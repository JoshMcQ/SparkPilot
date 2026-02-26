# AWS Auth Quickstart (IAM Access Keys)

This is the fastest path to run SparkPilot against a real AWS account for POCs.

## 1. Create IAM CLI User

In AWS Console:

1. Open `IAM` -> `Users` -> `Create user`.
2. User name: `sparkpilot-cli`.
3. Do **not** enable console access.
4. Permissions:
   - Choose `Attach policies directly`.
   - Select `AdministratorAccess` (temporary for first live test only).
5. Create user.

## 2. Create Access Key

1. Open user `sparkpilot-cli` -> `Security credentials`.
2. Click `Create access key`.
3. Use case: `Command Line Interface (CLI)`.
4. Confirm and create.
5. Copy:
   - `Access key ID`
   - `Secret access key` (shown once)

Do not commit keys to code or paste keys in chat/issues.

## 3. Configure AWS CLI

From PowerShell in repo root:

```powershell
python -m awscli configure
```

Enter:

- `AWS Access Key ID`: your key id
- `AWS Secret Access Key`: your secret key
- `Default region name`: `us-east-1`
- `Default output format`: `json`

## 4. Verify Credentials

```powershell
python -m awscli configure list
python -m awscli sts get-caller-identity
```

Expected `sts get-caller-identity` output shape:

```json
{
  "UserId": "...",
  "Account": "...",
  "Arn": "arn:aws:iam::<account-id>:user/sparkpilot-cli"
}
```

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named 'awscli'` | AWS CLI module missing | `python -m pip install awscli` |
| `Unable to locate credentials` | Keys were not saved | Re-run `python -m awscli configure` and enter all values |
| `configure list` shows `<not set>` | Enter pressed on prompts without values | Re-run `python -m awscli configure` |
| `An error occurred (AccessDenied)` | IAM policy too restrictive | For first live test, attach temporary `AdministratorAccess` to `sparkpilot-cli` |
| Calls hit wrong region/resources | Region mismatch | Set region to `us-east-1` in `configure` |
| `aws` launcher issues on Windows | Script wrapper/file association issue | Use `python -m awscli ...` commands |
