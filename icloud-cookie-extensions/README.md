# iCloud HME Cookie Bridge

## 安装

1. 打开 `chrome://extensions`。
2. 开启右上角“开发者模式”。
3. 点击“加载已解压的扩展程序”。
4. 选择本目录 `icloud-cookie-extensions`。
5. 刷新 `http://127.0.0.1:5050` 仪表盘。

## 使用

1. 在同一个 Chrome 配置中登录 iCloud。
2. 仪表盘选择账号，点击“更新 Cookie”。
3. 点击“从 Chrome 自动提取”。

扩展只响应 `127.0.0.1` / `localhost` 页面。Cookie 由扩展直接提交到本机服务，不进入仪表盘页面脚本。
