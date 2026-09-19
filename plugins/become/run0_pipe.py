# Copyright (c) 2026, Marcel Arpogaus
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt)
from __future__ import annotations

DOCUMENTATION = """
name: run0_pipe
short_description: Switch user with run0, without a TTY
description:
  - Uses C(run0 --pipe), which runs the command without a terminal, so the
    module source can be fed on stdin and pipelining works.
  - The upstream C(community.general.run0) plugin allocates a TTY, and a
    terminal line discipline corrupts a piped module. It therefore sets
    C(pipelining = False), which costs eight SSH operations per task instead
    of one.
  - This plugin expects a polkit rule that grants the action without
    authentication. Without one, C(run0) has no way to ask and the task fails.
author: Marcel Arpogaus (@MArpogaus)
options:
  become_user:
    description: User to become.
    default: root
    ini:
      - section: privilege_escalation
        key: become_user
      - section: run0_pipe_become_plugin
        key: user
    vars:
      - name: ansible_become_user
      - name: ansible_run0_pipe_user
    env:
      - name: ANSIBLE_BECOME_USER
      - name: ANSIBLE_RUN0_PIPE_USER
    type: string
  become_exe:
    description: The run0 executable.
    default: run0
    ini:
      - section: privilege_escalation
        key: become_exe
      - section: run0_pipe_become_plugin
        key: executable
    vars:
      - name: ansible_become_exe
      - name: ansible_run0_pipe_exe
    env:
      - name: ANSIBLE_BECOME_EXE
      - name: ANSIBLE_RUN0_PIPE_EXE
    type: string
  become_flags:
    description: Options to pass to run0.
    default: ''
    ini:
      - section: privilege_escalation
        key: become_flags
      - section: run0_pipe_become_plugin
        key: flags
    vars:
      - name: ansible_become_flags
      - name: ansible_run0_pipe_flags
    env:
      - name: ANSIBLE_BECOME_FLAGS
      - name: ANSIBLE_RUN0_PIPE_FLAGS
    type: string
"""

from ansible.plugins.become import BecomeBase


class BecomeModule(BecomeBase):
    name = "run0_pipe"

    prompt = ""
    fail = ("==== AUTHENTICATION FAILED ====",)
    require_tty = False
    pipelining = True

    def build_become_command(self, cmd, shell):
        super().build_become_command(cmd, shell)

        if not cmd:
            return cmd

        become = self.get_option("become_exe")
        flags = self.get_option("become_flags")
        user = self.get_option("become_user")

        return (
            f"SYSTEMD_COLORS=0 {become} --pipe --user={user} {flags} "
            f"{self._build_success_command(cmd, shell)}"
        )
