# -*- coding: utf-8 -*-
"""P0：私有 ACL 所有权交接的异常路径回归（371 复核 R1）。

复核发现：``_SecurityAttributes`` 构造与 ``_WindowsPrivateSecurity`` 所有权交接
原先位于异常清理区之外，若这两步抛 ``MemoryError``，本次分配的 SID 无人释放，
且调用方尚未拿到 security 对象、无法 close。本用例用注入方式覆盖这两个反例，
并确认成功路径不会重复释放。
"""

from __future__ import annotations

import ctypes
import os
import unittest
from unittest import mock

from scripts import role_provision as rp


@unittest.skipUnless(os.name == "nt", "Windows 私有 ACL")
class PrivateSecurityHandoffTests(unittest.TestCase):
    def setUp(self):
        self.freed: list[int] = []
        kernel32 = mock.Mock()
        kernel32.LocalFree.side_effect = lambda pointer: self.freed.append(
            int(getattr(pointer, "value", pointer) or 0)
        )
        advapi32 = mock.Mock()
        advapi32.InitializeAcl.return_value = 1
        advapi32.AddAccessAllowedAceEx.return_value = 1
        advapi32.InitializeSecurityDescriptor.return_value = 1
        advapi32.SetSecurityDescriptorDacl.return_value = 1
        counter = {"n": 0}

        def _to_sid(_text, out):
            counter["n"] += 1
            out._obj.value = 0x1000 + counter["n"]
            return 1

        advapi32.ConvertStringSidToSidW.side_effect = _to_sid

        self._patches = [
            mock.patch.object(rp, "_WINDOWS", True),
            mock.patch.object(rp, "_kernel32", kernel32),
            mock.patch.object(rp, "_advapi32", advapi32),
            mock.patch.object(
                rp, "_windows_acl_sids", lambda: ["S-1-5-18", "S-1-5-32-544"]
            ),
        ]
        for patcher in self._patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_attribute_construction_memoryerror_frees_sids(self):
        real_attributes = rp._SecurityAttributes

        class _Boom(real_attributes):  # type: ignore[misc, valid-type]
            def __new__(cls, *args, **kwargs):
                raise MemoryError("injected at _SecurityAttributes")

        with mock.patch.object(rp, "_SecurityAttributes", _Boom):
            with self.assertRaises(MemoryError):
                rp._windows_build_private_security_attributes()
        self.assertEqual(self.freed, [0x1001, 0x1002])

    def test_handoff_memoryerror_frees_sids(self):
        boom = mock.Mock(side_effect=MemoryError("injected at handoff"))
        with mock.patch.object(rp, "_WindowsPrivateSecurity", boom):
            with self.assertRaises(MemoryError):
                rp._windows_build_private_security_attributes()
        self.assertEqual(self.freed, [0x1001, 0x1002])

    def test_success_hands_ownership_and_close_is_idempotent(self):
        security = rp._windows_build_private_security_attributes()
        self.assertEqual(self.freed, [])
        security.close()
        self.assertEqual(self.freed, [0x1001, 0x1002])
        security.close()  # 幂等：不得重复释放
        self.assertEqual(self.freed, [0x1001, 0x1002])

    def test_partial_acl_failure_keeps_original_error_path(self):
        rp._advapi32.InitializeSecurityDescriptor.return_value = 0
        with self.assertRaises(rp._WindowsAclError):
            rp._windows_build_private_security_attributes()
        self.assertEqual(self.freed, [0x1001, 0x1002])


if __name__ == "__main__":
    unittest.main()
