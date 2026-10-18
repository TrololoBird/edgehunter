# Cloud session -> VPS deploy

A Claude Code cloud session works in its own checkout of `TrololoBird/edgehunter` and reaches the VPS as `claude-cloud`
(no root; created by `/root/setup-claude-cloud.sh` on the VPS). It can: deploy `origin/master`, roll back to an earlier
commit of it, read the bot's status and journal. It cannot read the secrets (`config.local.toml`, `/etc/edgehunter.env`)
or run anything else as root.

Cloud environment settings (claude.ai -> Code -> environment): network access to `194.247.182.162:22`; secrets
`EDGEHUNTER_VPS_HOST=194.247.182.162` and `EDGEHUNTER_VPS_KEY` (the private key in `/root/claude-cloud-key` on the VPS).
Setup command:

```bash
mkdir -p ~/.ssh && printf '%s\n' "$EDGEHUNTER_VPS_KEY" > ~/.ssh/edgehunter && chmod 600 ~/.ssh/edgehunter
```

## Workflow

1. Change the code on a branch; `python -m pytest tests -q`; `ruff check --select F --exclude .claude .`.
2. Bump `CONFIG.journal.logic_version` for any behaviour change (and `keep_waiting_from` when detection / planning /
   vetoes change).
3. Merge into `master` (fast-forward) and push `master`.
4. Deploy - one restart; the precheck failing rolls the tree back without a restart:

```bash
ssh -i ~/.ssh/edgehunter -o StrictHostKeyChecking=accept-new claude-cloud@$EDGEHUNTER_VPS_HOST sudo edgehunter-deploy
ssh -i ~/.ssh/edgehunter claude-cloud@$EDGEHUNTER_VPS_HOST sudo edgehunter-deploy <commit>     # back to an earlier commit of master
ssh -i ~/.ssh/edgehunter claude-cloud@$EDGEHUNTER_VPS_HOST sudo systemctl status edgehunter-bot
ssh -i ~/.ssh/edgehunter claude-cloud@$EDGEHUNTER_VPS_HOST journalctl -u edgehunter-bot -n 200 --no-pager
```

The VPS is never edited by hand: what runs is a commit of `origin/master`. Live-only files stay in place:
`config.local.toml` and the locally refit `models/overshoot.json` (backed up to `backup/` on every deploy).
