import Foundation

public enum LLMClient {
    /// Directly tests any OpenAI-compatible chat completions endpoint using native URLSession.
    public static func testConnection(
        baseURL: String,
        apiKey: String,
        model: String,
        session: URLSession = .shared
    ) async -> LLMTestResult {
        let key = apiKey.trimmingCharacters(in: .whitespacesAndNewlines)
        if key.isEmpty {
            return LLMTestResult(
                ok: false,
                message: "请先填写有效的 API Key（若已保存密钥可留空自动复用）。",
                latencyMs: nil,
                replyPreview: ""
            )
        }
        let endpoint = EndpointURLBuilder.chatCompletionsURL(from: baseURL)
        guard let url = URL(string: endpoint),
              let scheme = url.scheme?.lowercased(),
              (scheme == "http" || scheme == "https"),
              let host = url.host, !host.isEmpty
        else {
            return LLMTestResult(
                ok: false,
                message: "API 地址格式无效（需以 http:// 或 https:// 开头并包含有效主机名）：\(endpoint)",
                latencyMs: nil,
                replyPreview: ""
            )
        }

        let effectiveModel = model.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            ? "gpt-4o-mini"
            : model.trimmingCharacters(in: .whitespacesAndNewlines)

        var req = URLRequest(url: url, timeoutInterval: 20)
        req.httpMethod = "POST"
        req.setValue("Bearer \(key)", forHTTPHeaderField: "Authorization")
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")

        let payload: [String: Any] = [
            "model": effectiveModel,
            "max_tokens": 16,
            "temperature": 0.0,
            "messages": [
                ["role": "user", "content": "Reply with OK only."],
            ],
        ]
        guard let bodyData = try? JSONSerialization.data(withJSONObject: payload) else {
            return LLMTestResult(ok: false, message: "构造测试请求失败。", latencyMs: nil, replyPreview: "")
        }
        req.httpBody = bodyData

        let t0 = Date()
        do {
            let (data, response) = try await session.data(for: req)
            let ms = Int(Date().timeIntervalSince(t0) * 1000)
            guard let httpResp = response as? HTTPURLResponse else {
                return LLMTestResult(ok: false, message: "未收到有效 HTTP 响应。", latencyMs: ms, replyPreview: "")
            }
            if httpResp.statusCode < 200 || httpResp.statusCode >= 300 {
                let errText = extractErrorMessage(from: data) ?? "HTTP \(httpResp.statusCode)"
                return LLMTestResult(
                    ok: false,
                    message: "连接失败（HTTP \(httpResp.statusCode)）：\(errText)",
                    latencyMs: ms,
                    replyPreview: ""
                )
            }
            let reply = extractReplyPreview(from: data)
            return LLMTestResult(
                ok: true,
                message: "连接成功（\(effectiveModel)，耗时 \(ms) ms）",
                latencyMs: ms,
                replyPreview: reply
            )
        } catch {
            let ms = Int(Date().timeIntervalSince(t0) * 1000)
            return LLMTestResult(
                ok: false,
                message: "网络请求失败：\(error.localizedDescription)",
                latencyMs: ms,
                replyPreview: ""
            )
        }
    }

    private static func extractReplyPreview(from data: Data) -> String {
        guard let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let choices = obj["choices"] as? [[String: Any]],
              let first = choices.first,
              let message = first["message"] as? [String: Any],
              let content = message["content"] as? String
        else {
            return ""
        }
        return String(content.trimmingCharacters(in: .whitespacesAndNewlines).prefix(80))
    }

    private static func extractErrorMessage(from data: Data) -> String? {
        if let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
            if let errObj = obj["error"] as? [String: Any], let msg = errObj["message"] as? String {
                return String(msg.prefix(180))
            }
            if let msg = obj["message"] as? String {
                return String(msg.prefix(180))
            }
            if let detail = obj["detail"] as? String {
                return String(detail.prefix(180))
            }
        }
        if let raw = String(data: data, encoding: .utf8), !raw.isEmpty {
            return String(raw.trimmingCharacters(in: .whitespacesAndNewlines).prefix(180))
        }
        return nil
    }
}
