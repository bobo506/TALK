"""Human-operated registration of available WorkBuddy ACP models."""
import argparse
import json
import sys
from pathlib import Path
from urllib.parse import quote
import httpx
from bridges.workbuddy_acp import AcpError, acp_alias, list_models
from bridges.workbuddy_cdp import CdpError, list_models as list_cdp_models

def choice_payload(model, transport='acp'):
    # 内置模型与 models.json 的 custom-local 可能同名；加后缀避免创建角色时混淆。
    if transport == 'cdp':
        mid = model.get('model_id', model.get('modelId'))
        supported = model.get('supported_efforts', [])
        default = model.get('default_effort')
        if not isinstance(mid, str) or not mid or not isinstance(supported, list) or any(x not in ('low', 'high', 'max') for x in supported) or len(set(supported)) != len(supported) or (default is not None and default not in supported):
            raise ValueError('invalid model capabilities')
        capabilities = ['effort:' + x for x in ('low', 'high', 'max') if x in supported]
        if default is not None: capabilities.append('effort_default:' + default)
        return {'model_source':'builtin','provider_id':'managed:workbuddy','connection_ref':'native-workbuddy-cdp','model_id':mid,'model_alias':'workbuddy-cdp:' + mid,'model_display_name':(model.get('name') or mid) + '\uff08\u5185\u7f6e\u00b7\u684c\u9762\uff09', 'capabilities':capabilities}
    display = (model.get('name') or model['modelId']) + '（内置）'
    return {'model_source':'builtin','provider_id':'managed:workbuddy','connection_ref':'native-workbuddy-acp','model_id':model['modelId'],'model_alias':acp_alias(model['modelId']),'model_display_name':display}

def register(api_base, key, models, runner_id, available=None, transport='acp'):
    with httpx.Client(base_url=api_base.rstrip('/'), headers={'X-API-Key':key}, trust_env=False, timeout=30) as client:
        me = client.get('/api/members/me'); me.raise_for_status()
        if me.json().get('kind') != 'human': raise ValueError('human operator required')
        catalog = {(m['model_id'] if transport == 'cdp' else m['modelId']):m for m in (available if available is not None else (list_cdp_models() if transport == 'cdp' else list_models()))}
        if not models or any(mid not in catalog for mid in models): raise ValueError('model unavailable')
        payloads = [choice_payload(catalog[mid], transport) for mid in models]
        path = '/api/runners/' + quote(runner_id, safe='') + '/model-choices'
        existing = client.get(path, params={'include_retired':'true'}); existing.raise_for_status()
        rows = existing.json()
        if isinstance(rows,dict): rows = rows.get('data', rows.get('items', []))
        if not isinstance(rows,list): raise ValueError('invalid choices')
        results = []
        for payload in payloads:
            match = next ( (r for r in rows if (transport != 'cdp' or r.get('runner_id') == runner_id) and all(r.get(k)==payload[k] for k in ('model_source','provider_id','connection_ref','model_id','model_alias'))), None)
            if match:
                if transport == 'cdp':
                    old = match.get('capabilities') or []
                    capabilities = [c for c in old if not c.startswith(('effort:', 'effort_default:'))] + payload['capabilities']
                    if old != capabilities:
                        response = client.patch(path + '/' + quote(match['choice_id'], safe=''), json={'capabilities':capabilities}); response.raise_for_status()
                results.append({'status':'existing','choice_id':match.get('choice_id')})
            else:
                response = client.post(path, json=payload); response.raise_for_status(); row = response.json()
                results.append({'status':'created','choice_id':row.get('choice_id')})
        return results

def main(argv=None):
    parser=argparse.ArgumentParser(); sub=parser.add_subparsers(dest='action',required=True)
    ls=sub.add_parser('list'); ls.add_argument('--endpoint'); ls.add_argument('--transport', choices=('acp','cdp'), default='acp'); ls.add_argument('--models')
    reg=sub.add_parser('register'); reg.add_argument('--api-base',required=True); reg.add_argument('--operator-key-file',required=True); reg.add_argument('--models',required=True); reg.add_argument('--runner-id',default='runner:workbuddy-embedded-cli')
    reg.add_argument('--transport', choices=('acp','cdp'), default='acp')
    args=parser.parse_args(argv)
    try:
        if args.action == 'list':
            if args.transport == 'cdp':
                result=list_cdp_models(endpoint=args.endpoint)
                if args.models:
                    requested = [m.strip() for m in args.models.split(',') if m.strip()]
                    if not requested or any(mid not in {m['model_id'] for m in result} for mid in requested): raise ValueError('model unavailable')
                    result = [m for m in result if m['model_id'] in requested]
            else: result=list_models(args.endpoint)
        else:
            key=Path(args.operator_key_file).read_text(encoding='utf-8').strip()
            if not key: raise ValueError('empty key')
            result=register(args.api_base,key,[m.strip() for m in args.models.split(',') if m.strip()],args.runner_id, transport=args.transport)
        print(json.dumps(result,ensure_ascii=False)); return 0
    except CdpError as exc:
        print('[workbuddy-cdp] ' + exc.code, file=sys.stderr); return 2
    except ValueError as exc:
        print('[workbuddy-acp] ' + (str(exc) if str(exc) in ('model unavailable', 'invalid model capabilities') else 'registration_or_runtime_failed'), file=sys.stderr); return 2
    except (AcpError, OSError, httpx.HTTPError, KeyError):
        print('[workbuddy-acp] registration_or_runtime_failed',file=sys.stderr); return 2
if __name__=='__main__': raise SystemExit(main())
