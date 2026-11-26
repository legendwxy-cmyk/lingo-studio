import LingoReelCore
import SwiftUI

struct AISettingsTab: View {
    @ObservedObject var manager: ServiceManager
    let skin: LingoSkin

    @State private var draft: EngineSettings = EngineSettings(from: LingoReelConstants.defaultEngineSettings)
    @State private var llmKeyInput: String = ""
    @State private var asrKeyInput: String = ""
    @State private var clearLLMKey: Bool = false
    @State private var clearASRKey: Bool = false
    @State private var initialized: Bool = false

    private let asrModes: [(id: String, label: String)] = [
        ("auto", "智能自动（优先云端，失败自动回退本地 Whisper）"),
        ("local_whisper", "纯本地离线 Whisper（完全免费、零网络依赖）"),
        ("cloud_api", "强制使用云端 Whisper API"),
        ("subtitle_only", "仅解析上传字幕（不做语音识别）"),
    ]

    private let whisperModels: [String] = ["tiny.en", "base.en", "small.en", "tiny", "base", "small"]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                headerSection
                presetsCard
                llmConfigCard
                asrConfigCard
                saveFooter
            }
            .padding(24)
        }
        .onAppear {
            manager.reloadEngineSettings()
            syncFromManager()
            initialized = true
        }
        .onChange(of: manager.engineSettings) { _ in
            if initialized {
                syncFromManager()
            }
        }
    }

    private func syncFromManager() {
        draft = manager.engineSettings
        llmKeyInput = ""
        asrKeyInput = ""
        clearLLMKey = false
        clearASRKey = false
    }

    private var headerSection: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("AI 模型与语音转写配置")
                .font(.system(size: 22, weight: .black, design: .rounded))
                .foregroundColor(skin.ink)
            Text("与 Lingo 学习机网页共享同一份本机数据库；服务未启动前即可绑定密钥并直测大模型连通性。")
                .font(.system(size: 13, weight: .medium, design: .rounded))
                .foregroundColor(skin.inkMuted)
        }
    }

    private var presetsCard: some View {
        LingoCard(skin: skin, padding: 18) {
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    Text("快捷厂商预设")
                        .font(.system(size: 15, weight: .black, design: .rounded))
                        .foregroundColor(skin.ink)
                    LingoPill(skin: skin, text: "一键填入接口与推荐模型", tone: .accent)
                }

                Text("DeepSeek、通义千问、Gemini 兼容预设仅更新大模型地址，不会覆盖你自定义的云端语音转写配置。")
                    .font(.system(size: 12, weight: .medium, design: .rounded))
                    .foregroundColor(skin.inkMuted)

                LazyVGrid(
                    columns: [GridItem(.adaptive(minimum: 128), spacing: 10)],
                    alignment: .leading,
                    spacing: 10
                ) {
                    ForEach(ProviderPreset.all) { preset in
                        Button {
                            preset.apply(to: &draft)
                            manager.showToast("已填入「\(preset.label)」预设地址与模型，填写密钥后点击保存即可。")
                        } label: {
                            Text(preset.label)
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(Lingo3DButtonStyle(skin: skin, variant: .keycap, compact: true, fullWidth: true))
                    }
                }
            }
        }
    }

    private var llmConfigCard: some View {
        LingoCard(skin: skin, padding: 20) {
            VStack(alignment: .leading, spacing: 15) {
                HStack {
                    Text("大语言模型（字幕翻译 / 词条提取 / AI 精讲 / 复述评分）")
                        .font(.system(size: 15.5, weight: .black, design: .rounded))
                        .foregroundColor(skin.ink)
                    Spacer()
                    if manager.engineSettings.hasLLMKey && !clearLLMKey {
                        LingoPill(
                            skin: skin,
                            text: "已绑定 \(manager.engineSettings.llmAPIKey)",
                            tone: .mint,
                            mono: true
                        )
                    }
                }

                Divider()

                LingoFormRow(skin: skin, label: "API Base URL", hint: "兼容 OpenAI 格式，例如 https://api.deepseek.com/v1") {
                    LingoInputWell(skin: skin) {
                        TextField("https://api.openai.com/v1", text: $draft.llmBaseURL)
                            .font(.system(size: 13, weight: .medium, design: .monospaced))
                    }
                }

                LingoFormRow(skin: skin, label: "模型名称", hint: "例如 deepseek-chat / gpt-4o-mini / qwen-plus") {
                    LingoInputWell(skin: skin) {
                        TextField("gpt-4o-mini", text: $draft.llmModel)
                            .font(.system(size: 13, weight: .medium, design: .monospaced))
                    }
                }

                LingoFormRow(
                    skin: skin,
                    label: "API Key",
                    hint: manager.engineSettings.hasLLMKey && !clearLLMKey
                        ? "留空保留当前已保存密钥；粘贴新密钥可直接替换（支持 ⌘V）"
                        : "粘贴你的模型 API Key（仅保存在本机 SQLite 数据库中）"
                ) {
                    HStack(spacing: 8) {
                        LingoInputWell(skin: skin) {
                            SecureField(
                                manager.engineSettings.hasLLMKey && !clearLLMKey
                                    ? "已保存（\(manager.engineSettings.llmAPIKey)），留空不变"
                                    : "sk-...",
                                text: $llmKeyInput
                            )
                        }
                        .onChange(of: llmKeyInput) { val in
                            if !val.isEmpty { clearLLMKey = false }
                        }

                        if manager.engineSettings.hasLLMKey && !clearLLMKey {
                            Button("清除密钥") {
                                llmKeyInput = ""
                                clearLLMKey = true
                            }
                            .buttonStyle(Lingo3DButtonStyle(skin: skin, variant: .coral, compact: true))
                        }
                    }
                }

                HStack(spacing: 12) {
                    Button {
                        var testDraft = draft
                        if !llmKeyInput.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                            testDraft.llmAPIKey = llmKeyInput
                        } else if clearLLMKey {
                            testDraft.llmAPIKey = ""
                        }
                        Task {
                            await manager.testLLMConnection(
                                draft: testDraft,
                                allowStoredFallback: !clearLLMKey
                            )
                        }
                    } label: {
                        HStack(spacing: 6) {
                            if manager.isTestingLLM {
                                ProgressView().controlSize(.small)
                                Text("正在测试连接...")
                            } else {
                                Image(systemName: "bolt.horizontal.circle.fill")
                                Text("测试大模型连通性")
                            }
                        }
                    }
                    .buttonStyle(Lingo3DButtonStyle(skin: skin, variant: .accent, compact: true))
                    .disabled(manager.isTestingLLM)

                    if let res = manager.llmTestResult {
                        HStack(spacing: 6) {
                            Image(systemName: res.ok ? "checkmark.circle.fill" : "xmark.circle.fill")
                                .foregroundColor(res.ok ? skin.mintDeep : skin.coral)
                            Text(res.message)
                                .font(.system(size: 12.5, weight: .bold, design: .rounded))
                                .foregroundColor(res.ok ? skin.mintInk : skin.coral)
                                .lineLimit(2)
                        }
                        .padding(.horizontal, 10)
                        .padding(.vertical, 6)
                        .background(
                            RoundedRectangle(cornerRadius: 10, style: .continuous)
                                .fill(res.ok ? skin.mintSoft : skin.coralSoft)
                        )
                    }
                    Spacer()
                }
            }
        }
    }

    private var asrConfigCard: some View {
        LingoCard(skin: skin, padding: 20) {
            VStack(alignment: .leading, spacing: 15) {
                HStack {
                    Text("语音识别与跟读评测引擎（ASR）")
                        .font(.system(size: 15.5, weight: .black, design: .rounded))
                        .foregroundColor(skin.ink)
                    Spacer()
                    if manager.engineSettings.hasASRKey && !clearASRKey {
                        LingoPill(
                            skin: skin,
                            text: "已绑定 ASR \(manager.engineSettings.asrAPIKey)",
                            tone: .mint,
                            mono: true
                        )
                    }
                }

                Divider()

                LingoFormRow(skin: skin, label: "转写策略", hint: "推荐「智能自动」：无云端 Key 或超时时自动切本地离线 Whisper") {
                    Picker("", selection: $draft.asrMode) {
                        ForEach(asrModes, id: \.id) { item in
                            Text(item.label).tag(item.id)
                        }
                    }
                    .labelsHidden()
                }

                LingoFormRow(skin: skin, label: "本地 Whisper 模型", hint: "tiny.en 速度最快，base.en / small.en 识别更精准") {
                    Picker("", selection: $draft.localWhisperModel) {
                        ForEach(whisperModels, id: \.self) { m in
                            Text(m).tag(m)
                        }
                    }
                    .labelsHidden()
                    .frame(width: 180)
                }

                LingoFormRow(skin: skin, label: "云端 ASR Base URL", hint: "可选；支持 OpenAI Whisper / Groq / 硅基流动") {
                    LingoInputWell(skin: skin) {
                        TextField("https://api.openai.com/v1", text: $draft.asrBaseURL)
                            .font(.system(size: 13, weight: .medium, design: .monospaced))
                    }
                }

                LingoFormRow(skin: skin, label: "云端 ASR 模型", hint: "例如 whisper-1 / whisper-large-v3-turbo") {
                    LingoInputWell(skin: skin) {
                        TextField("whisper-1", text: $draft.asrModel)
                            .font(.system(size: 13, weight: .medium, design: .monospaced))
                    }
                }

                LingoFormRow(
                    skin: skin,
                    label: "云端 ASR API Key",
                    hint: manager.engineSettings.hasASRKey && !clearASRKey
                        ? "留空保留已保存密钥；未配置时自动使用本地离线 Whisper"
                        : "可选；不填也可使用内置本地离线 Whisper"
                ) {
                    HStack(spacing: 8) {
                        LingoInputWell(skin: skin) {
                            SecureField(
                                manager.engineSettings.hasASRKey && !clearASRKey
                                    ? "已保存（\(manager.engineSettings.asrAPIKey)），留空不变"
                                    : "可选（留空默认离线识别）",
                                text: $asrKeyInput
                            )
                        }
                        .onChange(of: asrKeyInput) { val in
                            if !val.isEmpty { clearASRKey = false }
                        }

                        if manager.engineSettings.hasASRKey && !clearASRKey {
                            Button("清除密钥") {
                                asrKeyInput = ""
                                clearASRKey = true
                            }
                            .buttonStyle(Lingo3DButtonStyle(skin: skin, variant: .coral, compact: true))
                        }
                    }
                }

                LingoFormRow(skin: skin, label: "在线词典补全", hint: "离线词库未收录生词时自动查询免费英英词典补全音标释义") {
                    Toggle("启用在线词典补全", isOn: $draft.enableOnlineDictFallback)
                        .toggleStyle(Lingo3DToggleStyle(skin: skin))
                }
            }
        }
    }

    private var saveFooter: some View {
        HStack {
            Text("密钥仅保存在本机用户目录下，不会上传至任何第三方服务器。")
                .font(.system(size: 12, weight: .medium, design: .rounded))
                .foregroundColor(skin.inkMuted)
            Spacer()
            Button("重置修改") {
                syncFromManager()
            }
            .buttonStyle(Lingo3DButtonStyle(skin: skin, variant: .white))

            Button("保存 AI 与语音配置") {
                var toSave = draft
                let trimmedLLM = llmKeyInput.trimmingCharacters(in: .whitespacesAndNewlines)
                let trimmedASR = asrKeyInput.trimmingCharacters(in: .whitespacesAndNewlines)
                if !trimmedLLM.isEmpty {
                    toSave.llmAPIKey = trimmedLLM
                } else if !clearLLMKey {
                    toSave.llmAPIKey = manager.engineSettings.llmAPIKey
                } else {
                    toSave.llmAPIKey = ""
                }
                if !trimmedASR.isEmpty {
                    toSave.asrAPIKey = trimmedASR
                } else if !clearASRKey {
                    toSave.asrAPIKey = manager.engineSettings.asrAPIKey
                } else {
                    toSave.asrAPIKey = ""
                }
                manager.saveEngineSettings(
                    toSave,
                    clearLLMKey: clearLLMKey,
                    clearASRKey: clearASRKey
                )
                llmKeyInput = ""
                asrKeyInput = ""
                clearLLMKey = false
                clearASRKey = false
            }
            .buttonStyle(Lingo3DButtonStyle(skin: skin, variant: .darkAccent))
        }
    }
}
