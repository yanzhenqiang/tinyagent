## CLI Reference

| Command | Description |
|---------|-------------|
| `tinyagent chat` | Interactive chat mode |
| `tinyagent message “xxxx”` | One message Mode |
| `tinyagent gateway` | Start the gateway |

## Create a Feishu bot
- Visit [Feishu Open Platform](https://open.feishu.cn/app)
- Create a new app → Enable **Bot** capability
- **Permissions**: Add `im:message` (send messages) and `im:message.p2p_msg:readonly` (receive messages)
- **Events**: Add `im.message.receive_v1` (receive messages)
  - Select **Long Connection** mode
- Get **App ID** and **App Secret** from "Credentials & Basic Info"
- Publish the app

```json
{
  "channels": {
    "feishu": {
      "enabled": true,
      "appId": "cli_xxx",
      "appSecret": "xxx",
      "encryptKey": "",
      "verificationToken": "",
      "allowFrom": ["ou_YOUR_OPEN_ID"],
      "groupPolicy": "mention"
    }
  }
}
```
> `encryptKey` and `verificationToken` are optional for Long Connection mode.
> `allowFrom`: Add your open_id. Use `["*"]` to allow all users.
> `groupPolicy`: `"mention"` (respond only when @mentioned), `"open"` (respond to all group messages). Private chats always respond.



