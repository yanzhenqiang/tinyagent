## Architecture

Agent always run and self-repair and self improve

### Bootstrap Flow

1 Agent启动 → 检测Guard是否启动，如果没有启动就启动 → LLM Loop → 启动外部通讯（比如Feishu）目的是外部消息可以改变自身状态
2 (只是分析)凌晨，上一次崩溃日志分析如有（分析日志要留着万一分析错误方便后续继续分析）
  (动作)如果分析需要改配置或者改代码，改动的地方需要是用git来管理起来的，然后提交修改，然后触发退出
  Guard需要一直监控agent的心跳，如果agent没有心跳了，需要拉起agent，如果继续卡死呢 需要先回退然后拉起，这些操作也需要有记录方便下一次crash分析
  用户主动触发的ctrl c等主动退出不需要拉起
3 然后当前健康状态检查，方便后续对比诊断
4. memory重整，（重新整理后怎么验证有效呢？我没有想明白）
                                 

## CLI Reference

| Command | Description |
|---------|-------------|
| `tinyagent chat` | Interactive chat mode (Terminal channel) |
| `tinyagent message "task"` | One-shot message mode |
| `tinyagent gateway` | Start Feishu gateway |
| `tinyagent guard` | Start Guard supervisor (production) |

### Development vs Production

```bash
# Development - run Agent directly
python -m tinyagent chat

# Production - run under Guard
python -m tinyagent guard
```

---

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
