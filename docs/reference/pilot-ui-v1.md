# Pilot UI v1 reference

The initial compact pilot interface is preserved for design reference at
`pilot-ui-v1.html`. The complete runnable state is the annotated Git tag
`pilot-ui-v1` (`529b4c9`).

To inspect that full state without replacing the current working tree:

```bash
git worktree add /tmp/fluency-pilot-ui-v1 pilot-ui-v1
cd /tmp/fluency-pilot-ui-v1
make dev
```

The production development path is `app/index.html`, which is based on the
original Fluency product shell.
