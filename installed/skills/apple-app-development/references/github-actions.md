# GitHub Actions：产品发布与站点构建流程

按任务选择下列流程。有站点资源的应用仓库使用两份独立 workflow；只接入项目实际需要的方案。已有 workflow 时直接整理现有文件，不并排增加重复任务。模板面向 GitHub.com 托管 runner。

| 任务 | 执行流程 | 可复制模板 |
|---|---|---|
| 产品版本 tag 发布 | 流程一：发布前准备、签名打包、发布 Release | [product-release.yml](../assets/product-release.yml) |
| 站点资源构建 | 流程二：路径触发、站点检查、构建与产物处理 | [website-build.yml](../assets/website-build.yml) |

## 流程一：产品 tag 发布

### 1. 适配项目入口

复制模板到 `.github/workflows/product-release.yml`，已有同类 workflow 则在原文件接入。先核对并适配：

| 适配项 | 模板默认值及处理 |
|---|---|
| 发布说明 | 模板读取附注 tag 的正文；按版本准备流程在推送前写入本批次发布说明，已有发布说明渠道则直接沿用 |
| 构建环境 | 单个 `macos-15` runner；按实际架构和工具链调整，加入项目依赖准备 |
| 打包命令 | `bash scripts/build-dmg.sh`；改为项目已有入口，由它完成 [构建、签名、DMG 封装与清理](build-and-package.md) |
| 交付路径 | `dist/*.dmg`；改为实际最终包路径，已有多架构需求才保留矩阵和按架构区分的产物名 |
| 签名身份 | 变量 `MACOS_SIGNING_IDENTITY` 填固定的 Apple Development 身份，或沿用项目已有身份配置 |

### 2. 配置 tag 触发与权限

仅配置 `push.tags: ['v*']`，不添加普通分支 push、站点 PR 或手动分支发布。使用 tag 事件默认检出的提交，不重新检出主分支。发布分支限制在创建 tag 前确认。

构建 job 使用 `contents: read`，发布 job 使用 `contents: write` 且 `needs: build`。并发组使用 `product-release-${{ github.ref }}`，不取消正在执行的同 tag 发布。GitHub 不对 tag push 执行路径过滤，不用 `paths-ignore` 控制产品发布。

### 3. 在触发 Action 前完成发布准备

执行 [versioning.md](versioning.md) 的发布准备流程，确认本批次版本、变更记录、拟用 tag 和目标提交，准备附注 tag 正文中的发布说明。检查与准备必须在创建、推送 tag 前完成；推送后才触发本 workflow。Action 消费已确定的输入，不重新判断版本或提取 changelog，也不传递临时发布说明 artifact。

### 4. 导入证书并调用打包入口

首次接入或证书轮换时，用已授权材料配置 Secrets `MACOS_CERTIFICATE_P12_BASE64`、`MACOS_CERTIFICATE_PASSWORD`；已有值直接复用。模板将证书导入一次性 runner 的临时钥匙串，再调用步骤 1 确认的 Release 打包入口。

构建、签名和封装全部由该脚本执行，workflow 不复制这些命令。任何步骤失败即停止，不更换证书或降级签名。模板的 `always()` 步骤负责清理 P12 和临时钥匙串；本机、自托管 runner 改用其已有搜索列表保留与恢复机制。

### 5. 上传最终包并发布 Release

打包成功后上传最终 DMG，临时 Actions artifact 默认保留 7 天，不上传工作目录或过程报告。清理签名材料后，构建 job 成功才进入发布 job；多架构时等待全部目标成功。

发布 job 只下载本次运行的产物，以 `gh release create --notes-from-tag --verify-tag` 使用已准备的 tag 正文发布 Release 并附加 DMG。`--verify-tag` 限制该命令只能消费已有 tag，避免它自动创建 tag；这不是重新核对版本。已有同名 Release 时报告失败，不自动覆盖。

### 6. 核对运行结果

首次接入或修改 workflow 后完成 YAML／Shell 校验与相关命令验证；实际 Actions 验证结合已获授权的发布执行，不为测试而额外发布版本。日常运行使用各步骤日志与退出状态报告构建、上传和发布结果，不重新检查已由上游保证的版本和包内容。

## 流程二：站点构建

### 1. 适配站点入口与输入

复制模板到 `.github/workflows/website-build.yml`，已有同类 workflow 则在原文件接入。按项目实际情况适配：

| 适配项 | 模板默认值及处理 |
|---|---|
| 站点目录与分支 | `website/`、`main`；改为实际目录与生产分支 |
| 共享输入 | 将构建读取的应用元数据、图标、锁文件及生成脚本加入触发路径 |
| 工具链 | Node 24；沿用项目版本或版本文件，不为套模板更换前端工具链 |
| 构建入口 | `node website/build.mjs`；适用于无第三方依赖的静态构建，有依赖时先按锁文件安装，再运行已有构建命令 |
| 输出 | `website/dist/`；改为实际静态输出，构建入口成功即表示完整产物已生成 |

### 2. 配置路径触发与权限

在生产分支 push、普通 `pull_request` 上配置站点目录、workflow 自身和步骤 1 确认的共享输入路径，并保留 `workflow_dispatch` 手动检查入口。不配置产品 tag 触发。

使用 Linux runner 和 `contents: read`，不读取 Apple 签名 Secrets。并发组为 `website-build-${{ github.ref }}`，同一分支的新检查可取消旧检查。路径过滤跳过的 workflow 不设为所有 PR 无条件必需的检查，避免无关 PR 等待未运行的任务。

### 3. 构建站点

检出本次提交，准备工具链和依赖，运行项目已有的站点构建入口。构建成功即进入产物处理，不在 workflow 中追加文件存在性或内容断言。构建入口不能保证完整结果时，在开发阶段修复并验证该入口，不靠下游检查补齐。失败即停止后续产物上传或部署。此流程不执行应用签名、DMG 打包或产品版本更新。

### 4. 处理站点产物与部署

默认上传静态输出，供检查或后续部署消费，Actions artifact 保留 7 天；不上传源码目录、依赖目录或环境配置。只需要构建检查且无人消费产物时，删除上传步骤。

按项目已有托管方式选择一个衔接方式：

| 当前托管方式 | 执行动作 |
|---|---|
| Vercel 等平台已连接 Git 自动部署 | Actions 到构建检查结束，部署由原平台负责，不再增加重复部署 |
| 已有 GitHub Pages 或其他 Actions 部署 job | 构建成功后交给原部署 job 消费产物；仅生产分支或明确的手动发布进入生产部署，PR 只做检查 |
| 没有部署需求 | 上传所需产物或完成检查后结束 |

站点使用 GitHub Releases 稳定页面或 latest 下载链接时，不因每次产品发布重建站点；只有构建实际依赖发布数据时，才接入发布后的站点更新。

### 5. 核对运行结果

首次接入或修改 workflow 后，完成 YAML／Shell 校验、本地构建与产物验证，再通过已授权的实际运行验证路径触发和部署衔接。日常运行依靠构建、上传与部署命令的退出状态及日志；PR 不进入生产部署。

交付时区分本地构建、Actions 运行、产物上传和线上部署；复制或校验模板不等于远端执行成功，也不隐含推送 tag、发布 Release 或部署站点的授权。

技术依据：[GitHub 触发与路径过滤](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)、[证书导入与清理](https://docs.github.com/en/actions/how-tos/deploy/deploy-to-third-party-platforms/sign-xcode-applications)、[Release 创建与标签校验](https://cli.github.com/manual/gh_release_create)。模板 Action 用法见 [checkout](https://github.com/actions/checkout)、[setup-node](https://github.com/actions/setup-node)、[upload-artifact](https://github.com/actions/upload-artifact)、[download-artifact](https://github.com/actions/download-artifact)。
