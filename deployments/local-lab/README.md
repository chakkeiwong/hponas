# HPO-NAS local lab

This directory is the named development deployment under `~/workspace`.
`manage.py` creates its private PostgreSQL data, credentials, certificate,
artifact root and role profiles under `.hponas-runtime/deployments/local-lab`.
Generated `profiles/` files describe those locations without copying secrets.

From the project root, use `/home/ubuntu/miniforge3/bin/python` with:

```
deployments/local-lab/manage.py prepare
deployments/local-lab/manage.py start
deployments/local-lab/manage.py status
deployments/local-lab/manage.py stop
```

`start` starts only this lab's PostgreSQL. The once-allocated `verify` command
also runs a temporary two-worker Ray cluster and stops both owned services when
finished. Each invocation writes a new receipt directory. Verification is
development evidence, not a new official scientific allocation; retain every
outcome and refresh the allocation before another verification run.

Runtime and monitor connections use TLS with hostname verification and separate
SCRAM passwords. Maintenance uses local peer authentication through a private
socket. The database binds only to loopback. No system database, cloud resources
or remote services are created. The certificate is for this local lab and expires
after 30 days; stop and explicitly refresh the profile before further use then.

The finite verification checks six four-update quadratic trials, exact known
answers, study restart, role restrictions, invalid TLS/auth refusal, quiesced
backup, permanently fenced historical restore and database crash/restart.
The installed wheel/source identity is checked before starting. A code change
requires a reviewed new installation binding.

This folder represents one physical host. Its separate processes allow local
service/failure tests. Independent-machine loss, network partitions between
machines, remote artifact storage and unattended operations remain separate
APP-11 requirements in the master. Configuration can be generated here; those
external topology facts cannot be established by directory creation.
