# 01 – AWS setup: S3 + laptop access

Goal: by the end of this guide `aws s3 ls s3://YOUR-BUCKET` works from your laptop,
and there is no key anywhere in the repo.

Estimated time: 45–60 min (can be split into 2 sessions: steps 0–2 and steps 3–6).

---

## Concepts in 2 minutes

| concept | what it is | analogy |
|---|---|---|
| **Region** | physical location of an AWS data center. Here: `us-east-1` (N. Virginia). A bucket lives in one region. | a server in a specific server room |
| **Bucket** | a "container" for files in S3. The name is **globally unique** (across all of AWS, not just your account). | a network drive / share |
| **Object** | a file in a bucket. | a file |
| **Key / prefix** | the full "path" of an object, e.g. `raw/contracts/dt=2026-10-09/contracts.csv`. **Folders don't really exist in S3** – the console just draws them from the slashes in the name. | a file path |
| **IAM** | the service that manages identities and permissions. | Active Directory + folder permissions |
| **IAM user** | an identity for a person or a program. We create a user just for this project. | a service account |
| **Policy** | a JSON document: "who can do which action on which resource". | a folder permission list |
| **ARN** | a unique resource identifier, e.g. `arn:aws:s3:::my-bucket`. | a full UNC path |
| **Access key** | an *Access Key ID* + *Secret Access Key* pair – login and password for programs (CLI, DuckDB). | ODBC login/password |

**Least privilege:** the project user can access **only one bucket**.
If a key ever leaks, the damage is limited to synthetic data.

---

## Step 0 – Clean up EC2 (so nothing keeps billing)

AWS console → search for **EC2** → make sure the region in the top-right corner is the one where the instance was.

1. **Instances** → select the instance → *Instance state* → **Terminate (delete) instance**.
   (Stop is not enough – a stopped instance still pays for its disk.)
2. **Elastic Block Store → Volumes** – delete any volume left in the *available* state.
3. **Network & Security → Elastic IPs** – if an address is allocated, *Release Elastic IP address*.
4. **Elastic Block Store → Snapshots** – delete any snapshots.

## Step 1 – Account security and a cost alert (free)

1. **MFA on the root account** (if not set yet): click the account name (top right) → *Security credentials* → *Assign MFA device* → an authenticator app (Google Authenticator / Microsoft Authenticator).
2. **Budget with an alert:** search → **Billing and Cost Management** → *Budgets* → *Create budget* →
   template **Zero spend budget** → enter your e-mail → *Create budget*.
   You'll get an e-mail as soon as the account spends a single cent. The first 2 budgets are free.

## Step 2 – Create the bucket

Search → **S3** → *Create bucket*:

| field | value | why |
|---|---|---|
| AWS Region | **US East (N. Virginia) us-east-1** | our region |
| Bucket type | **General purpose** | standard S3 |
| Bucket name | e.g. `leasing-dbt-<something-unique>` (lowercase letters, digits, hyphens only) | must be unique across all of AWS |
| Object Ownership | **ACLs disabled** (default) | permissions only via IAM policies – simpler |
| Block Public Access | **Block all public access – CHECKED** (default) | data will never be public |
| Bucket Versioning | **Disable** | versioning would multiply files = costs |
| Default encryption | **SSE-S3** (default) | encryption at rest, free |

*Create bucket*. **Note the bucket name** – you'll need it in step 3.

Check: bucket → *Permissions* tab → *Block public access (bucket settings)* should say **On**.
*Bucket policy* stays empty – we grant permissions on the IAM user (identity-based policy), not on the bucket (resource-based policy).

## Step 3 – IAM user with access to this bucket only

Search → **IAM** → *Users* → *Create user*:

1. User name: `leasing-dbt-local`.
   **Do NOT** check "Provide user access to the AWS Management Console" – this user doesn't need the console, only a key for programs. → *Next*.
2. Permissions options: **Attach policies directly**, but don't select any managed policy → *Next* → *Create user*.
3. Open the new user → *Permissions* tab → *Add permissions* → **Create inline policy** → switch the editor to **JSON** and paste (replace `YOUR-BUCKET` in two places):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ListBucket",
      "Effect": "Allow",
      "Action": ["s3:ListBucket", "s3:GetBucketLocation"],
      "Resource": "arn:aws:s3:::YOUR-BUCKET"
    },
    {
      "Sid": "ReadWriteObjects",
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
      "Resource": "arn:aws:s3:::YOUR-BUCKET/*"
    }
  ]
}
```

4. *Next* → Policy name: `leasing-dbt-s3-access` → *Create policy*.

**How to read this policy:**
- The first block applies to **the bucket itself** (ARN without `/*`): listing its contents is allowed. DuckDB needs this to expand a pattern like `raw/contracts/*/*.csv`.
- The second block applies to **objects in the bucket** (ARN with `/*`): read, write, delete files. The generator writes, dbt reads.
- Anything not listed is **denied by default** – e.g. listing other buckets, EC2, deleting the bucket.

## Step 4 – Access key

User `leasing-dbt-local` → *Security credentials* tab → *Access keys* → **Create access key** →
use case: **Command Line Interface (CLI)** → tick the confirmation → *Next* → (description optional) → *Create access key*.

⚠️ **You see the Secret Access Key only once.** Keep the page open until step 5.

**Never:**
- paste keys into an AI chat or into any file in the project,
- take screenshots that show the key (including the terminal during `aws configure`),
- commit them to git.

If a key does leak: create a new key, run `aws configure` with it, then deactivate and delete the old one.

The only place the keys end up is `C:\Users\<you>\.aws\credentials` (outside the repo), created for you by `aws configure`.

## Step 5 – AWS CLI on Windows

In PowerShell (or download the MSI installer from the AWS "Install AWS CLI v2 Windows" page):

```powershell
winget install --id Amazon.AWSCLI -e
```

**Close and reopen the terminal** (to refresh PATH), then:

```powershell
aws --version
aws configure
```

`aws configure` asks for 4 things – type them **yourself, in your own terminal**:

```
AWS Access Key ID:      <from step 4>
AWS Secret Access Key:  <from step 4>
Default region name:    us-east-1
Default output format:  json
```

If it asks about configuring AWS skills / an MCP server for AI coding agents, answer `n`.

Now you can close the key page in the console.

## Step 6 – Tests

```powershell
# 1. Who am I? Should show an ARN ending with user/leasing-dbt-local
aws sts get-caller-identity

# 2. List my bucket (empty = no output, but NO error)
aws s3 ls s3://YOUR-BUCKET

# 3. Write, read, delete a test file
"test" | Out-File test.txt
aws s3 cp test.txt s3://YOUR-BUCKET/test/test.txt
aws s3 ls s3://YOUR-BUCKET/test/
aws s3 rm s3://YOUR-BUCKET/test/test.txt
Remove-Item test.txt

# 4. NEGATIVE test – this MUST fail (AccessDenied).
#    Proof that the policy really limits access to one bucket.
aws s3 ls
```

✅ Done if tests 1–3 pass and test 4 ends with `AccessDenied`.

---

### Next

Step 7: install `uv` → Python 3.12 → venv in the project → `dbt-core` + `dbt-duckdb`.

### Troubleshooting

| symptom | cause |
|---|---|
| `aws` is not recognized | terminal not restarted after install |
| `InvalidClientTokenId` / `SignatureDoesNotMatch` | typo in the keys → run `aws configure` again |
| `AccessDenied` in test 2 or 3 | typo in the bucket name in the policy or in the command |
| `NoSuchBucket` | wrong bucket name or a different region |
