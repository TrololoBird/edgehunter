# Cloud session -> VPS deploy

A Claude Code cloud session works in its own checkout of `TrololoBird/pump` and reaches the VPS as `claude-cloud`
(no root; created by `/root/setup-claude-cloud.sh` on the VPS). It can: deploy `origin/master`, roll back to an earlier
commit of it, read the bot's status and journal. It cannot read the secrets (`config.local.toml`, `/etc/pump-bot.env`)
or run anything else as root.

Cloud environment settings (claude.ai -> Code -> environment): network access to `194.247.182.162:22`; secrets
`PUMP_VPS_HOST=194.247.182.162` and `PUMP_VPS_KEY` (the private key in `/root/claude-cloud-key` on the VPS).
Setup command:

```bash
mkdir -p ~/.ssh && printf '%s\n' "$PUMP_VPS_KEY" > ~/.ssh/pump && chmod 600 ~/.ssh/pump
```

## Workflow

1. Change the code on a branch; `python -m pytest tests -q`; `ruff check --select F --exclude .claude .`.
2. Bump `CONFIG.journal.logic_version` for any behaviour change (and `keep_waiting_from` when detection / planning /
   vetoes change).
3. Merge into `master` (fast-forward) and push `master`.
4. Deploy - one restart; the precheck failing rolls the tree back without a restart:

```bash
ssh -i ~/.ssh/pump -o StrictHostKeyChecking=accept-new claude-cloud@$PUMP_VPS_HOST sudo pump-deploy
ssh -i ~/.ssh/pump claude-cloud@$PUMP_VPS_HOST sudo pump-deploy <commit>     # back to an earlier commit of master
ssh -i ~/.ssh/pump claude-cloud@$PUMP_VPS_HOST sudo systemctl status pump-bot
ssh -i ~/.ssh/pump claude-cloud@$PUMP_VPS_HOST journalctl -u pump-bot -n 200 --no-pager
```

The VPS is never edited by hand: what runs is a commit of `origin/master`. Live-only files stay in place:
`config.local.toml` and the locally refit `models/overshoot.json` (backed up to `backup/` on every deploy).
