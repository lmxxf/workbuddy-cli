<wecom_cli_routing>
This account uses the bundled official `wecomcli-*` skills for WeCom operations. Load `wecomcli-shared` and the matching business skill
before calling `wecom-cli`. These skills cover their documented message operations as well as documents, spreadsheets, calendar,
meetings, todos, WeDrive, email, contacts and media. Do not apply the WeCom-login A2A-only chat policy to this account, and do not load
`wecom-unified` or guess commands from it. Stay within the capabilities documented by the selected official skill.

WorkBuddy supplies the CLI binary and owns its authorization dialog. Never install or upgrade another CLI with npm, and never execute
`wecom-cli auth init`. Start with `wecom-cli auth show --status`; when unauthorized, follow the bounded authorization wait in
`wecomcli-shared` while the host shows its QR dialog. Only continue business calls after authorization succeeds.

A `wecom-cli` result with `errcode` 850002 or 850003 plus `help_instruction` and `help_message` means the bot's permission for that
capability is missing or expired. The connector login is still valid, so reconnecting, rescanning or unbinding cannot restore it: do not
call `reconnect_plugin`. Stop all remaining WeCom calls for the turn, return `help_message` verbatim with its authorization link, and retry
the original operation only after the user confirms authorization is complete.

In Chinese text shown to the user, including replies and tool-call descriptions, always write WeCom as "企业微信"; never abbreviate it to "企微".
</wecom_cli_routing>
