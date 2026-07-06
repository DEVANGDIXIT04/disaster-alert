# Serverless notification function (AWS Lambda)

`notify_lambda.py` answers one question: **"given an incident at (lat, lng), which
users live close enough to be alerted?"**

The same file runs in two ways — this is the key point to explain in the viva:

| Where | How it runs |
|---|---|
| Locally / on Elastic Beanstalk | `app.py` imports `find_nearby_users()` and calls it like any function |
| AWS Lambda | AWS invokes `lambda_handler(event, context)` on demand — no server of ours |

The file uses **only the Python standard library**, so deploying it is just
zipping one file. When invoked without a `users` list in the event it falls
back to a small built-in demo list, so it can be tested from the AWS console
with nothing else set up. (A production version would query RDS here —
see Future Scope in the main README.)

## Deploy it (copy-paste, ~2 minutes)

From the `serverless/` folder:

```bash
# 1. Zip the single file (PowerShell version of zip):
powershell Compress-Archive -Force -Path notify_lambda.py -DestinationPath function.zip

# 2. One-time: create an execution role the function will run as.
aws iam create-role --role-name disaster-alert-lambda-role `
  --assume-role-policy-document "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Principal\":{\"Service\":\"lambda.amazonaws.com\"},\"Action\":\"sts:AssumeRole\"}]}"

# Let it write logs to CloudWatch (that's all it needs):
aws iam attach-role-policy --role-name disaster-alert-lambda-role `
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole

# 3. Create the function (replace <ACCOUNT_ID> with your 12-digit account id):
aws lambda create-function `
  --function-name disaster-alert-notify `
  --runtime python3.12 `
  --handler notify_lambda.lambda_handler `
  --zip-file fileb://function.zip `
  --role arn:aws:iam::<ACCOUNT_ID>:role/disaster-alert-lambda-role
```

(If you edit the code later: re-zip, then
`aws lambda update-function-code --function-name disaster-alert-notify --zip-file fileb://function.zip`)

## Test it

```bash
aws lambda invoke --function-name disaster-alert-notify `
  --cli-binary-format raw-in-base64-out `
  --payload "{\"lat\": 28.61, \"lng\": 77.36, \"radius_km\": 5}" `
  response.json

cat response.json
```

Expected output — the demo users who live within 5 km of Noida Sector 62:

```json
{"alerted_users": [{"id": 1, "name": "Abhijeet", ...distance_km: 0.0},
                   {"id": 2, "name": "Viyom", ...distance_km: 2.4}],
 "count": 2}
```

You can also test in the **AWS console**: Lambda → disaster-alert-notify →
Test tab → paste the same JSON event. The `print()` output (the simulated
alert) appears in the execution log / CloudWatch Logs.

## Clean up

```bash
aws lambda delete-function --function-name disaster-alert-notify
aws iam detach-role-policy --role-name disaster-alert-lambda-role --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
aws iam delete-role --role-name disaster-alert-lambda-role
```
