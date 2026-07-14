import { defineConfig } from 'vitepress'
import type { PluginOption } from 'vite'
import { groupIconMdPlugin, groupIconVitePlugin,localIconLoader } from 'vitepress-plugin-group-icons'
import { 
  GitChangelog, 
  GitChangelogMarkdownSection, 
} from '@nolebase/vitepress-plugin-git-changelog/vite'
import {
  PageProperties,
  PagePropertiesMarkdownSection,
} from '@nolebase/vitepress-plugin-page-properties/vite'

const base = '/nekobot/'

export default defineConfig({
  base,
  vite: {
    optimizeDeps: {
      exclude: [ 
        '@nolebase/vitepress-plugin-enhanced-readabilities/client', 
        'vitepress', 
        '@nolebase/ui', 
      ], 
    },
    ssr: { 
      noExternal: [ 
        // 如果还有别的依赖需要添加的话，并排填写和配置到这里即可
        '@nolebase/vitepress-plugin-highlight-targeted-heading', 
        '@nolebase/vitepress-plugin-enhanced-readabilities', 
        '@nolebase/ui', 
      ], 
    }, 
    plugins: [
      PageProperties(),
      PagePropertiesMarkdownSection({
        excludes: ['index.md'],
      }),
      groupIconVitePlugin(
        { 
        customIcon: {
          ts: 'logos:typescript',
          js: 'logos:javascript', //js图标
          md: 'logos:markdown', //markdown图标
          css: 'logos:css-3', //css图标
          python:'logos:python',
          cpp:'logos:c-plus-plus',
          c:'logos:c'
        },
        }
      ), //代码组图标
      GitChangelog({
        repoURL: () => 'https://github.com/asukaneko/nekobot',
        limit: 20,
      }), 
      GitChangelogMarkdownSection({
        sections: {
          // 禁用页面历史
          disableChangelog: false,
          // 禁用贡献者
          disableContributors: true,
        },
      }) as any,
    ],
  }, 
  title: "NekoBot",
  description: "多频道 AI 机器人 - QQ / Web / Telegram",
  lang: 'zh-CN',
  head: [['link', { rel: 'icon', href: `${base}neko.png` }]],
  themeConfig: {
    docFooter: { 
      prev: '上一页', 
      next: '下一页', 
    }, 
    outline: { 
      level: [2,4], // 显示2-4级标题
      label: '当前页大纲' // 文字显示
    },
    lastUpdated: {
      text: '最后更新于',
      formatOptions: {
        dateStyle: 'short', // 可选值full、long、medium、short
        timeStyle: 'medium' // 可选值full、long、medium、short
      },
    },
    logo: `${base}neko.png`,
    nav: [
      { text: '主页', link: '/' },
      { text: '快速开始', link: '/guide/quick-start.md' },
      { text: '开发指南', link: '/guide/guide.md' },
      { 
        text: 'GitHub',
        link: 'https://github.com/asukaneko/Ncatbot-comic-QQbot'
      }
    ],
    sidebar: {
      '/guide/': [
        {
          text: '快速上手',
          collapsed: false,
          items: [
            { text: '快速开始', link: '/guide/quick-start.md' },
            { text: 'Docker 部署', link: '/guide/docker-deploy.md' },
            { text: '所有命令', link: '/guide/commands.md' },
            { text: '更新日志', link: '/guide/changelog.md' },
          ]
        },
        {
          text: '项目开发',
          collapsed: true,
          items: [
            { text: '开发指南', link: '/guide/guide.md' },
            { text: '频道管理与接入', link: '/guide/channels.md' },
          ]
        },
{
              text: 'nbot 核心模块',
              collapsed: true,
              items: [
                {
                  text: 'core - AI核心',
                  collapsed: true,
                  items: [
                    { text: 'ai_pipeline - 管道中间件', link: '/guide/nbot/core/ai_pipeline.md' },
                    { text: 'chat_models - 聊天模型', link: '/guide/nbot/core/chat_models.md' },
                    { text: 'agent_service - AI服务', link: '/guide/nbot/core/agent_service.md' },
                    { text: 'session_store - 会话存储', link: '/guide/nbot/core/session_store.md' },
                    { text: 'model_adapter - 模型适配', link: '/guide/nbot/core/model_adapter.md' },
                    { text: 'protocols - 多协议适配', link: '/guide/nbot/core/protocols.md' },
                    { text: 'workspace - 工作区', link: '/guide/nbot/core/workspace.md' },
                    { text: 'workflow - 工作流', link: '/guide/nbot/core/workflow.md' },
                    { text: 'token_stats - Token用量统计', link: '/guide/nbot/core/token_stats.md' },
                    { text: 'failover - 故障转移', link: '/guide/nbot/core/failover.md' },
                    { text: 'file_parser - 文件解析', link: '/guide/nbot/core/file_parser.md' },
                    { text: 'message_middleware - 消息中间件', link: '/guide/nbot/core/message_middleware.md' },
                    { text: 'message - 统一消息', link: '/guide/nbot/core/message.md' },
                    { text: 'prompt - 提示词管理', link: '/guide/nbot/core/prompt.md' },
                    { text: 'switches - 开关管理', link: '/guide/nbot/core/switches.md' },
                    { text: 'heartbeat - 心跳引擎', link: '/guide/nbot/core/heartbeat.md' },
                    { text: 'background_tasks - 后台任务调度', link: '/guide/nbot/core/background_tasks.md' },
                    {
                      text: '协议详细实现',
                      collapsed: true,
                      items: [
                        { text: 'OpenAI Chat', link: '/guide/nbot/core/protocols/openai_chat.md' },
                        { text: 'OpenAI Responses', link: '/guide/nbot/core/protocols/openai_responses.md' },
                        { text: 'Anthropic Messages', link: '/guide/nbot/core/protocols/anthropic_messages.md' },
                        { text: 'Gemini Native', link: '/guide/nbot/core/protocols/gemini_native.md' },
                      ]
                    },
                  ]
                },
                {
                  text: 'character - 实时情感引擎',
                  collapsed: true,
                  items: [
                    { text: 'index - 概述', link: '/guide/nbot/character/index.md' },
                    { text: 'models - 数据模型', link: '/guide/nbot/character/models.md' },
                    { text: 'prompt_stack - 动态提示词栈', link: '/guide/nbot/character/prompt_stack.md' },
                    { text: 'runtime - 运行时引擎', link: '/guide/nbot/character/runtime.md' },
                    { text: 'planner - 反应计划生成器', link: '/guide/nbot/character/planner.md' },
                    { text: 'state_machine - 状态机', link: '/guide/nbot/character/state_machine.md' },
                    { text: 'policies - 信号分析器', link: '/guide/nbot/character/policies.md' },
                    { text: 'memory - 角色记忆服务', link: '/guide/nbot/character/memory.md' },
                    { text: 'repository - 数据仓库', link: '/guide/nbot/character/repository.md' },
                    { text: 'world_book - 世界书', link: '/guide/nbot/character/world_book.md' },
                  ]
                },
                {
                  text: 'channels - 频道层',
                  collapsed: true,
                  items: [
                    { text: 'add-channel - 新增频道', link: '/guide/nbot/channels/add-channel.md' },
                    { text: 'base - 频道基类', link: '/guide/nbot/channels/base.md' },
                    { text: 'registry - 频道注册', link: '/guide/nbot/channels/registry.md' },
                    { text: 'qq - QQ适配器', link: '/guide/nbot/channels/qq.md' },
                    { text: 'qqbot - QQ官方机器人', link: '/guide/nbot/channels/qqbot.md' },
                    { text: 'web - Web适配器', link: '/guide/nbot/channels/web.md' },
                    { text: 'telegram - Telegram适配器', link: '/guide/nbot/channels/telegram.md' },
                  ]
                },
                {
                  text: 'services - 服务层',
                  collapsed: true,
                  items: [
                    { text: 'ai - AI客户端', link: '/guide/nbot/services/ai.md' },
                    { text: 'tts - 语音合成', link: '/guide/nbot/services/tts.md' },
                    { text: 'stt - 语音识别', link: '/guide/nbot/services/stt.md' },
                    { text: 'sticker_service - 表情包服务', link: '/guide/nbot/services/sticker_service.md' },
                    { text: 'image_service - 图片生成服务', link: '/guide/nbot/services/image_service.md' },
                    { text: 'tools - 工具系统', link: '/guide/nbot/services/tools.md' },
                    { text: 'chat_service - 聊天服务', link: '/guide/nbot/services/chat_service.md' },
                    { text: 'todo_tools - 待办工具', link: '/guide/nbot/services/todo_tools.md' },
                    { text: 'feishu - 飞书集成', link: '/guide/nbot/services/feishu.md' },
                    { text: 'telegram - Telegram集成', link: '/guide/nbot/services/telegram.md' },
                    { text: 'mcp_bridge - MCP桥接', link: '/guide/nbot/services/mcp_bridge.md' },
                    { text: 'react - ReAct代理', link: '/guide/nbot/services/react.md' },
                    { text: 'tts_config - TTS配置', link: '/guide/nbot/services/tts_config.md' },
                  ]
                },
                { 
                  text: 'plugins - 插件系统',
                  collapsed: true,
                  items: [
                    { text: 'skills - 技能系统', link: '/guide/nbot/plugins/skills.md' },
                    { text: 'dispatcher - 调度器', link: '/guide/nbot/plugins/dispatcher.md' },
                  ]
                },
                {
                  text: 'gateway - 消息网关层',
                  collapsed: true,
                  items: [
                    { text: '概述', link: '/guide/nbot/gateway/index.md' },
                    { text: '处理管线', link: '/guide/nbot/gateway/pipeline.md' },
                    { text: '安全认证与限流', link: '/guide/nbot/gateway/security.md' },
                    { text: '存储与追踪', link: '/guide/nbot/gateway/storage.md' },
                    { text: '队列与投递', link: '/guide/nbot/gateway/delivery.md' },
                    { text: '内部任务', link: '/guide/nbot/gateway/internal-tasks.md' },
                    { text: '节点控制平面', link: '/guide/nbot/gateway/nodes.md' },
                    { text: '限流策略', link: '/guide/nbot/gateway/rate_limit.md' },
                    { text: '消息去重', link: '/guide/nbot/gateway/dedupe.md' },
                    { text: 'TTS处理', link: '/guide/nbot/gateway/tts_handler.md' },
                    { text: '事件总线', link: '/guide/nbot/gateway/bus.md' },
                  ]
                },
                {
                  text: 'mcp - AI Agent 接口',
                  collapsed: true,
                  items: [
                    { text: '概述', link: '/guide/nbot/mcp/index.md' },
                    { text: 'Gateway Tools', link: '/guide/nbot/mcp/tools.md' },
                    { text: 'Web Tools', link: '/guide/nbot/mcp/web_tools.md' },
                    { text: '配置', link: '/guide/nbot/mcp/config.md' },
                    { text: 'MCP Client', link: '/guide/nbot/mcp/client.md' },
                  ]
                },
                {
                  text: 'web - Web后台',
                  collapsed: true,
                  items: [
                    { text: 'server - 服务入口', link: '/guide/nbot/web/server.md' },
                    { text: 'routes - API路由', link: '/guide/nbot/web/routes.md' },
                    { text: 'file_gateway - 文件网关', link: '/guide/nbot/web/file_gateway.md' },
                    { text: 'webdav_backup - WebDAV 备份同步', link: '/guide/nbot/web/webdav_backup.md' },
                    { text: 'socket_events - Socket事件', link: '/guide/nbot/web/socket_events.md' },
                    { text: 'sessions_db - 会话数据库', link: '/guide/nbot/web/sessions_db.md' },
                    { text: 'persistence - 数据持久化', link: '/guide/nbot/web/persistence.md' },
                    { text: 'secure_store - 安全存储', link: '/guide/nbot/web/secure_store.md' },
                  ]
                },
                {
                  text: 'cli - 命令行界面',
                  collapsed: true,
                  items: [
                    { text: '概述', link: '/guide/nbot/cli/index.md' },
                  ]
                },
                {
                  text: 'hooks - 钩子事件驱动系统',
                  collapsed: true,
                  items: [
                    { text: '概述', link: '/guide/nbot/hooks/index.md' },
                    { text: '事件参考', link: '/guide/nbot/hooks/events.md' },
                    { text: '条件参考', link: '/guide/nbot/hooks/conditions.md' },
                    { text: '动作参考', link: '/guide/nbot/hooks/actions.md' },
                    { text: 'Web API 参考', link: '/guide/nbot/hooks/web-api.md' },
                    { text: 'Web 管理界面', link: '/guide/nbot/hooks/web-ui.md' },
                    { text: '使用示例', link: '/guide/nbot/hooks/examples.md' },
                  ]
                },
                {
                  text: 'plot - 剧情图与分支故事',
                  collapsed: true,
                  items: [
                    { text: '概述', link: '/guide/nbot/plot/index.md' },
                    { text: 'models - 数据模型', link: '/guide/nbot/plot/models.md' },
                    { text: 'graph_manager - 剧情图管理器', link: '/guide/nbot/plot/graph_manager.md' },
                    { text: 'choice_generator - 选择生成器', link: '/guide/nbot/plot/choice_generator.md' },
                    { text: 'bridges - 桥接模块', link: '/guide/nbot/plot/bridges.md' },
                  ]
                },
                {
                  text: 'group - 群聊会话系统',
                  collapsed: true,
                  items: [
                    { text: '概述', link: '/guide/nbot/group/index.md' },
                    { text: 'models - 数据模型', link: '/guide/nbot/group/models.md' },
                    { text: 'scheduler - 调度器', link: '/guide/nbot/group/scheduler.md' },
                    { text: 'narrator - 旁白系统', link: '/guide/nbot/group/narrator.md' },
                    { text: 'cross_talk - 跨角色对话', link: '/guide/nbot/group/cross_talk.md' },
                  ]
                },
                {
                  text: 'events - 事件标准化系统',
                  collapsed: true,
                  items: [
                    { text: '概述', link: '/guide/nbot/events/index.md' },
                    { text: '事件名称参考', link: '/guide/nbot/events/names.md' },
                  ]
                },
                {
                  text: 'memory - MemoryFS 记忆文件系统',
                  collapsed: true,
                  items: [
                    { text: '概述', link: '/guide/nbot/memory/index.md' },
                    { text: 'models - 数据模型', link: '/guide/nbot/memory/models.md' },
                    { text: 'fs - 文件系统', link: '/guide/nbot/memory/fs.md' },
                  ]
                },
                {
                  text: 'review - Review Pipeline 审查层',
                  collapsed: true,
                  items: [
                    { text: '概述', link: '/guide/nbot/review/index.md' },
                    { text: 'models - 数据模型', link: '/guide/nbot/review/models.md' },
                    { text: 'pipeline - 审查管线', link: '/guide/nbot/review/pipeline.md' },
                    { text: 'self_correction - 自我修正', link: '/guide/nbot/review/self_correction.md' },
                    { text: 'time_context - 现实时间连续性', link: '/guide/nbot/review/time_context.md' },
                  ]
                },
                {
                  text: 'world - WorldEngine 群聊判定器',
                  collapsed: true,
                  items: [
                    { text: '概述', link: '/guide/nbot/world/index.md' },
                    { text: 'engine - 判定引擎', link: '/guide/nbot/world/engine.md' },
                  ]
                },
              ]
            },
            {
              text: '高级指南',
              collapsed: true,
              items: [
                { text: 'MCP 集成指南', link: '/guide/advanced/mcp-integration.md' },
                { text: '消息过滤器', link: '/guide/advanced/message-filter.md' },
              ]
            },
            {
              text: '常见问题',
              collapsed: true,
              items: [
                { text: 'FAQ', link: '/guide/faq/index.md' },
              ]
            }
      ],
      '/napcat/':[
        {
          text:'快速上手',
          link:'/guide/quick-start.md'
        },
        {
          text:'基础',
          items: [
            { text: '主页', link: '/napcat/index.md' },
            { text: '接入框架', link: '/napcat/integration.md' },
            { text: '社区资源', link: '/napcat/community.md' },
          ]
        },
        {
          text:'协议',
          collapsed: true,
          items: [
            { text: 'API 接口', link: '/napcat/api.md' },
            { text: '事件基础结构', link: '/napcat/basic_event.md' },
            { text: '事件字段详情', link: '/napcat/event.md' },
            { text: '网络通讯', link: '/napcat/network.md' },
            { text: '消息元素定义', link: '/napcat/msg.md' },
          ]
        }
      ]
    },

    socialLinks: [
      { icon: 'github', link: 'https://github.com/asukaneko/Ncatbot-comic-QQbot' }
    ],

    search: {
      provider: 'local'
    },
    footer: {
      message: 'Released under the <a href="https://github.com/asukaneko/Ncatbot-comic-QQbot/blob/main/LICENSE">MIT License</a>.',
      copyright: 'Copyright © 2025-present <a href="https://github.com/asukaneko">Asukaneko</a>'
    },
    editLink: {
      pattern: 'https://github.com/asukaneko/Ncatbot-comic-QQbot/edit/main/docs/docs/:path',
      text: '在 GitHub 上编辑此页'
    }
  },
  ignoreDeadLinks: true,
  markdown: {
    container: {
      tipLabel: '提示',
      warningLabel: '警告',
      dangerLabel: '危险',
      infoLabel: '信息',
      detailsLabel: '详细信息'
    },
    math: true,
    image: {
      // 开启图片懒加载
      lazyLoading: true
    },
    // 组件插入h1标题下
    config(md) {
      // 创建 markdown-it 插件
      md.use(groupIconMdPlugin) //代码组图标
      md.use((md) => {
        const defaultRender = md.render
        md.render = function (...args) {
          const [content, env] = args
          const isHomePage = env.path === '/' || env.relativePath === 'index.md'  // 判断是否是首页

          if (isHomePage) {
            return defaultRender.apply(md, args) // 如果是首页，直接渲染内容
          }
          // 在每个 md 文件内容的开头插入组件
          const defaultContent = defaultRender.apply(md, args)
          const component = '<ArticleMetadata />\n'
          return component + defaultContent
        }
      })
    }
  },
  lastUpdated: true
})
