"""Explicit project startup preferences and one bounded, replay-safe activation.

Ordinary reads never start services. Only the bound local runtime's current
generation can execute saved choices; service ownership is never adopted.
"""
from datetime import datetime,timedelta,timezone
import hashlib
import json
import math
from pathlib import Path
import re
import secrets
import socket
import time

from fastapi import HTTPException
from sqlmodel import select
from server import models as m
from server.role_services import (_as_utc,_now,_write_begin,load_role_service_context,
    _require_managed_cli,_enqueue_start_launch,_idempotent_stopped,ownership_held,project_role_service,expire_due_launches)

TERMINAL={"enqueued","already_running","not_selected","skipped","failed"}
LEASE_SECONDS=120
ROUND_SECONDS=55
PROOF_RESERVE_SECONDS=45

def fail(code):raise HTTPException(409,code)
def human(operator):
    if operator.kind!='human':raise HTTPException(403,'only human members can configure project startup')
def public_entry(row):
    return {'status':row.status,'error_code':row.error_code,'launch_id':row.launch_id,
            'updated_at':_as_utc(row.updated_at).isoformat()}
def projection(project,member,session):
    pref=session.get(m.ProjectRoleStartup,(project,member))
    recent=session.exec(select(m.RoleStartupActivation).where(
        m.RoleStartupActivation.project_id==project,m.RoleStartupActivation.member_id==member
    ).order_by(m.RoleStartupActivation.created_at.desc()).limit(1)).first()
    return {'enabled':bool(pref and pref.enabled),'revision':pref.revision if pref else 0,
            'updated_at':_as_utc(pref.updated_at).isoformat() if pref else None,
            'last_activation':public_entry(recent) if recent else None}

def set_preference(project,member,enabled,operator,session):
    human(operator);_write_begin(session)
    try:
        ctx=load_role_service_context(project,member,session)
        if enabled:_require_managed_cli(ctx)
        pref=session.get(m.ProjectRoleStartup,(project,member))
        if pref is None and not enabled:
            session.rollback();return projection(project,member,session)
        if pref is None:
            pref=m.ProjectRoleStartup(project_id=project,member_id=member,enabled=enabled,updated_by=operator.id)
        elif pref.enabled==enabled:
            session.rollback();return projection(project,member,session)
        else:
            pref.enabled=enabled;pref.revision+=1;pref.updated_at=_now();pref.updated_by=operator.id
        session.add(pref);session.commit()
        return projection(project,member,session)
    except Exception:
        session.rollback();raise

def verified_runtime(project,activation,session):
    """No caller-provided path, PID or boot time is accepted as evidence."""
    from server.local_runtime import configured_runtime
    from scripts.role_service_recovery import recorded_process_state,system_boot_time
    from scripts.role_service_host import _parse_iso
    from bridges.runtime_log_retention import pinned,NativeFile
    try:
        bound=configured_runtime(session.get_bind())
        if bound is None or bound[1]['project_id']!=project:fail('startup_local_runtime_unbound')
        config=bound[1];path=Path(config['state_dir'])/'runtime'/'health.json'
        with pinned(path.parent),NativeFile(path) as file:
            health=json.loads(file.read(1024*1024))
        seen=_parse_iso(health.get('seen_at'));started=_parse_iso(health.get('started_at'))
        if (health.get('schema')!='talk-runtime-health-1' or health.get('project_id')!=project
                or health.get('activation_id')!=activation or health.get('state')!='running'
                or health.get('startup_state') not in ('pending','processing','complete')
                or health.get('stopping') or seen is None or started is None
                or not 0<=( _now()-seen).total_seconds()<30
                or type(health.get('pid')) is not int
                or recorded_process_state(health['pid'],health['started_at'])!='present'):
            fail('startup_runtime_unverified')
        boot=system_boot_time()
        cutoff=datetime.fromtimestamp(boot-2,timezone.utc) if boot is not None else None
        return config,health,cutoff
    except HTTPException:raise
    except Exception as exc:raise HTTPException(409,'startup_runtime_unverified') from exc

def _snapshot(project,activation,operator,session,health):
    _write_begin(session)
    try:
        cycle=session.get(m.ProjectStartupCycle,(project,activation))
        if cycle:
            if cycle.runtime_pid!=health['pid']:fail('startup_runtime_conflict')
            session.rollback();return
        members=session.exec(select(m.ProjectAgent).where(m.ProjectAgent.project_id==project)).all()
        if len(members)>128:fail('startup_role_limit')
        now=_now()
        from scripts.role_service_host import _parse_iso
        started=_parse_iso(health['started_at'])
        if started is None:fail('startup_runtime_unverified')
        session.add(m.ProjectStartupCycle(project_id=project,activation_id=activation,
                    runtime_pid=health['pid'],runtime_started_at=started,created_by=operator.id,created_at=now))
        for member in members:
            pref=session.get(m.ProjectRoleStartup,(project,member.member_id))
            state=session.get(m.RoleServiceState,(project,member.member_id))
            changed=bool(pref and _as_utc(pref.updated_at)>=started)
            manual=bool(state and _as_utc(state.updated_at)>=started)
            session.add(m.RoleStartupActivation(project_id=project,activation_id=activation,
                member_id=member.member_id,enabled=bool(pref and pref.enabled),
                preference_revision=pref.revision if pref else 0,
                status='skipped' if changed or manual else 'pending',
                error_code='startup_choice_changed' if changed else 'startup_manual_intent_present' if manual else None,
                expected_generation=int(state.generation) if state else 0,created_at=now,updated_at=now))
        session.commit()
    except Exception:
        session.rollback();raise

def _claim(key,session):
    _write_begin(session)
    row=session.get(m.RoleStartupActivation,key);now=_now()
    if row.status in TERMINAL or (row.status=='processing' and row.lease_expires_at
                                 and _as_utc(row.lease_expires_at)>now):
        session.rollback();return None
    token=secrets.token_urlsafe(24);digest=hashlib.sha256(token.encode()).hexdigest()
    row.status='processing';row.lease_hash=digest;row.lease_expires_at=now+timedelta(seconds=LEASE_SECONDS)
    row.updated_at=now;session.add(row);session.commit()
    return digest

def _locked_entry(key,digest,session):
    row=session.get(m.RoleStartupActivation,key)
    if (row is None or row.status!='processing' or row.lease_hash!=digest or not row.lease_expires_at
            or _as_utc(row.lease_expires_at)<=_now()):fail('startup_execution_conflict')
    return row
def _generation(row,session):
    state=session.get(m.RoleServiceState,(row.project_id,row.member_id))
    if (int(state.generation) if state else 0)!=row.expected_generation:fail('startup_manual_intent_present')
    pref=session.get(m.ProjectRoleStartup,(row.project_id,row.member_id))
    if (pref.revision if pref else 0)!=row.preference_revision:fail('startup_choice_changed')
    return state
def _finish(row,status,error=None,launch=None):
    row.status=status;row.error_code=error;row.launch_id=launch
    row.lease_hash=None;row.lease_expires_at=None;row.updated_at=_now()

def _ready(state,current,cutoff):
    # A quick OS reboot can leave a <90s DB heartbeat. That old process cannot
    # be ready in this boot; require the full cold-recovery identity proof.
    current_boot=bool(state and state.process_started_at and cutoff is not None
                      and _as_utc(state.process_started_at)>=cutoff)
    return bool(current_boot and current and current.observed=='running' and current.readiness_service=='ready')

def _complete(key,digest,status,session,*,launch=None):
    # Keep the final health/lease check beside commit. Flushed launch/state
    # changes roll back if the runtime stopped while checks were executing.
    verified_runtime(key[0],key[1],session)
    row=_locked_entry(key,digest,session)
    _finish(row,status,launch=launch);session.add(row);session.commit()

def _cold_recover(key,digest,operator,session,config,cutoff):
    """Only proven preboot ownership; current-boot failures remain manual."""
    from server.role_service_recovery import candidate,recover_stopped
    from scripts.role_service_recovery import local_proof
    from scripts.role_service_host import _sanitize_token,HostError
    row=session.get(m.RoleStartupActivation,key);state=_generation(row,session)
    if not ownership_held(state):return
    if cutoff is None:fail('startup_boot_unverified')
    old,instance=candidate(key[0],key[2],session,_now(),_preboot_at=cutoff)
    if old.owner_host.casefold()!=socket.gethostname().casefold():fail('recovery_wrong_local_host')
    spec=next((s for s in config.get('hosts',[]) if s['member_id']==key[2]),None)
    if spec:
        health=Path(spec['health_file'])
        entry=next((Path(a) for a in spec['argv'][1:] if a.endswith('.py')),None)
    elif config.get('workbuddy'):
        health=Path(config['state_dir'])/'workbuddy-native'/_sanitize_token(key[0])/_sanitize_token(key[2])/'manager-health.json'
        entry=Path(__file__).resolve().parents[1]/'scripts/workbuddy_role_host.py'
    else:fail('startup_host_unconfigured')
    if entry is None:fail('local_recovery_entry_unverified')
    plan={'project_id':key[0],'member_id':key[2],'expected_generation':old.generation,
          'expected_process_launch_id':old.process_launch_id,'expected_instance_id':old.observed_instance_id,
          'expected_owner_host':old.owner_host,'process_pid':old.pid,
          'instance_last_seen_at':_as_utc(instance.last_seen_at).isoformat(),
          'process_started_at':_as_utc(old.process_started_at).isoformat()}
    try:
        # Health must itself belong to the previous OS boot; never infer this from age.
        manager=json.loads(health.read_text(encoding='utf-8'))
        from scripts.role_service_host import _parse_iso
        if _parse_iso(manager.get('seen_at')) is None or _parse_iso(manager['seen_at'])>=cutoff:
            fail('recovery_not_previous_boot')
        proof=local_proof(plan,health,entry,_preboot_at=cutoff)
        if local_proof(plan,health,entry,_preboot_at=cutoff)!=proof:fail('recovery_local_evidence_changed')
    except HTTPException:raise
    except (HostError,OSError,ValueError) as exc:
        raise HTTPException(409,getattr(exc,'code','local_recovery_unverified')) from exc
    def audit(recovery,locked_session):
        verified_runtime(key[0],key[1],locked_session)
        current=_locked_entry(key,digest,locked_session)
        if current.expected_generation != recovery.previous_generation:fail('startup_manual_intent_present')
        pref=locked_session.get(m.ProjectRoleStartup,(key[0],key[2]))
        if (pref.revision if pref else 0)!=current.preference_revision:fail('startup_choice_changed')
        current.expected_generation=recovery.generation;current.recovery_id=recovery.recovery_id
        current.updated_at=_now();locked_session.add(current)
    body=m.RoleServiceRecoveryRequest(operation_key='startup-'+key[1]+'-'+hashlib.sha256(key[2].encode()).hexdigest()[:20],
        **{k:v for k,v in plan.items() if k.startswith('expected_')},
        confirmation='old_processes_confirmed_stopped',reason='original_host_exited')
    recover_stopped(key[0],key[2],body,operator,session,_preboot_at=cutoff,_on_recovered=audit)

def _apply(key,digest,operator,session):
    config,health,cutoff=verified_runtime(key[0],key[1],session)
    row=session.get(m.RoleStartupActivation,key);state=_generation(row,session)
    ctx=load_role_service_context(key[0],key[2],session)
    current=project_role_service(key[0],key[2],session)
    # Preserve an already ready service; do not call a stale running DB row ready.
    already=_ready(state,current,cutoff)
    if ownership_held(state) and not already:
        _cold_recover(key,digest,operator,session,config,cutoff)
    _write_begin(session)
    row=_locked_entry(key,digest,session);state=_generation(row,session)
    verified_runtime(key[0],key[1],session)
    expire_due_launches(session,now=_now(),project_id=key[0],member_id=key[2])
    ctx=load_role_service_context(key[0],key[2],session)
    current=project_role_service(key[0],key[2],session)
    already=_ready(state,current,cutoff)
    if already:
        _complete(key,digest,'already_running',session);return
    if ownership_held(state):fail('startup_recovery_required')
    launch=session.get(m.RoleServiceLaunch,state.current_launch_id) if state and state.current_launch_id else None
    old_unclaimed=bool(cutoff is not None and launch and launch.action=='start'
        and launch.state in ('pending','expired') and launch.claim_host is None
        and launch.claimed_at is None and _as_utc(launch.created_at)<cutoff)
    if state and (state.observed_state in ('starting','running') or old_unclaimed):
        if not old_unclaimed:
            fail('startup_existing_intent')
        # A never-claimed preboot start has no child; invalidate it and persist
        # the activation's new baseline in the same ordinary stop transaction.
        row.expected_generation=int(state.generation)+1;session.add(row)
        verified_runtime(key[0],key[1],session)
        _locked_entry(key,digest,session)
        _idempotent_stopped(key[0],key[2],ctx.role.role_name,state,session,_now(),operator)
        _write_begin(session);row=_locked_entry(key,digest,session);state=_generation(row,session)
        verified_runtime(key[0],key[1],session)
        ctx=load_role_service_context(key[0],key[2],session)
    if state and state.observed_state in ('unknown','stopping'):fail('startup_recovery_required')
    if not row.enabled:
        _complete(key,digest,'not_selected',session);return
    _require_managed_cli(ctx)
    verified_runtime(key[0],key[1],session)
    _locked_entry(key,digest,session)
    launch=_enqueue_start_launch(ctx,key[0],key[2],session=session,now=_now(),
                                 actor_id='system:project-startup',expected_generation=row.expected_generation)
    _complete(key,digest,'enqueued',session,launch=launch.launch_id)

def activate(project,activation,operator,session):
    human(operator);deadline=time.monotonic()+ROUND_SECONDS
    config,health,cutoff=verified_runtime(project,activation,session)
    _snapshot(project,activation,operator,session,health)
    keys=[(project,activation,r.member_id) for r in session.exec(select(m.RoleStartupActivation).where(
        m.RoleStartupActivation.project_id==project,m.RoleStartupActivation.activation_id==activation
    ).order_by(m.RoleStartupActivation.member_id)).all()]
    for key in keys:
        if deadline-time.monotonic()<PROOF_RESERVE_SECONDS:break
        verified_runtime(project,activation,session)
        digest=_claim(key,session)
        if digest is None:continue
        try:_apply(key,digest,operator,session)
        except Exception as exc:
            session.rollback()
            code=getattr(exc,'detail',None) or getattr(exc,'code',None)
            code=code if isinstance(code,str) and re.fullmatch(r'[a-z][a-z0-9_]{0,79}',code) else 'project_startup_failed'
            try:
                _write_begin(session);row=_locked_entry(key,digest,session)
                _finish(row,'skipped' if code in ('startup_manual_intent_present','startup_choice_changed','startup_existing_intent') else 'failed',code)
                session.add(row);session.commit()
            except HTTPException:session.rollback()  # A newer lease owns the result.
    session.expire_all()
    rows=session.exec(select(m.RoleStartupActivation).where(
        m.RoleStartupActivation.project_id==project,m.RoleStartupActivation.activation_id==activation
    ).order_by(m.RoleStartupActivation.member_id)).all()
    waits=[(_as_utc(r.lease_expires_at)-_now()).total_seconds() for r in rows
           if r.status=='processing' and r.lease_expires_at]
    retry=5 if any(r.status=='pending' for r in rows) else max(5,min(120,math.ceil(min(waits))+1)) if waits else 5
    return {'activation_id':activation,'complete':all(r.status in TERMINAL for r in rows),'retry_after_seconds':retry,
            'results':[{'member_id':r.member_id,**public_entry(r)} for r in rows]}
