# Attach GET + POST `/settings` to an existing API Gateway HTTP API

Use this when `/data` and `/ingest` already work but **POST /settings** returns API Gateway’s plain `{"message":"Not Found"}` because no route exists.

## What to deploy in Lambda

Package these files at the **zip root** (same layout as this repo’s `lambda/` folder):

- `settings_handler.py`
- `update_settings.py` (optional shim: `update_settings.lambda_handler` → same code)
- `shared/__init__.py`
- `shared/dynamo_settings.py`

Handler string: **`settings_handler.lambda_handler`**

Environment variables (match your other Lambdas):

- `SETTINGS_TABLE_NAME` — DynamoDB table with partition key `id` (string), row `global` for thresholds.

## CloudFormation (HTTP API v2)

Parameters:

- `HttpApiId` — API id from the invoke URL (e.g. `9jzbd9a34j`).
- `SettingsLambdaArn` — full ARN of the Lambda above.

```yaml
AWSTemplateFormatVersion: '2010-09-09'
Description: Add GET/POST /settings routes to an existing HTTP API (AWS_PROXY to Lambda)

Parameters:
  HttpApiId:
    Type: String
    Description: HTTP API id (from execute-api URL hostname prefix)
  SettingsLambdaArn:
    Type: String
    Description: ARN of the settings Lambda (settings_handler.lambda_handler)

Resources:
  SettingsIntegration:
    Type: AWS::ApiGatewayV2::Integration
    Properties:
      ApiId: !Ref HttpApiId
      IntegrationType: AWS_PROXY
      IntegrationUri: !Ref SettingsLambdaArn
      PayloadFormatVersion: '2.0'

  SettingsPermission:
    Type: AWS::Lambda::Permission
    Properties:
      Action: lambda:InvokeFunction
      FunctionName: !Ref SettingsLambdaArn
      Principal: apigateway.amazonaws.com
      SourceArn: !Sub arn:aws:execute-api:${AWS::Region}:${AWS::AccountId}:${HttpApiId}/*/*/*

  SettingsRouteGet:
    Type: AWS::ApiGatewayV2::Route
    Properties:
      ApiId: !Ref HttpApiId
      RouteKey: GET /settings
      Target: !Sub integrations/${SettingsIntegration}

  SettingsRoutePost:
    Type: AWS::ApiGatewayV2::Route
    Properties:
      ApiId: !Ref HttpApiId
      RouteKey: POST /settings
      Target: !Sub integrations/${SettingsIntegration}

Outputs:
  SettingsGetRouteId:
    Value: !Ref SettingsRouteGet
  SettingsPostRouteId:
    Value: !Ref SettingsRoutePost
```

**Note:** `AWS::AccountId` and `AWS::Region` pseudo-parameters are resolved automatically. If `SourceArn` is too broad or too narrow for your account policy, narrow to `.../${HttpApiId}/*/POST/settings` and a second permission for GET — some teams use one permission with `/*/*/*`.

After deploy, **OPTIONS** for CORS is handled inside the Lambda (204 + CORS headers). If your API uses a separate CORS configuration, you may still add `OPTIONS /settings` as another route to the same integration.

## Verify

```bash
curl -sS "https://<api-id>.execute-api.<region>.amazonaws.com/settings"
curl -sS -X POST "https://<api-id>.execute-api.<region>.amazonaws.com/settings" \
  -H "Content-Type: application/json" \
  -d '{"temp_min":0,"temp_max":40,"humidity_min":20,"humidity_max":80,"pressure_min":980,"pressure_max":1030}'
```

Both should return **JSON** (not bare `Not Found`). Errors from the Lambda use `{ "success": false, "error": "...", "message": "..." }`.
