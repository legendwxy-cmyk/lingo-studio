package main

import (
	"bufio"
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"encoding/xml"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"regexp"
	"runtime"
	"sort"
	"strconv"
	"strings"
	"syscall"
	"time"
)

const (
	consoleLabel   = "com.lingoreel.studio.console"
	nativeGuiLabel = "com.lingoreel.studio.nativegui"
)

type logger struct {
	file *os.File
}

func newLogger(path string) *logger {
	_ = os.MkdirAll(filepath.Dir(path), 0o755)
	f, err := os.OpenFile(path, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o644)
	if err != nil {
		return &logger{}
	}
	return &logger{file: f}
}

func (l *logger) Printf(format string, args ...any) {
	line := fmt.Sprintf("[%s] %s\n", time.Now().Format("2006-01-02 15:04:05"), fmt.Sprintf(format, args...))
	if l.file != nil {
		_, _ = l.file.WriteString(line)
	}
}

func (l *logger) Close() {
	if l.file != nil {
		_ = l.file.Close()
	}
}

func bootoutLegacyWebConsole(log *logger) {
	if runtime.GOOS != "darwin" {
		return
	}
	target := "gui/" + strconv.Itoa(os.Getuid()) + "/" + consoleLabel
	if err := exec.Command("/bin/launchctl", "bootout", target).Run(); err == nil {
		log.Printf("booted out legacy web console agent: %s", target)
	}
}

func computeFrontendBuildID(frontendDist string) string {
	markerPath := filepath.Join(frontendDist, ".lingo_build_id")
	if raw, err := os.ReadFile(markerPath); err == nil {
		if val := strings.TrimSpace(string(raw)); val != "" {
			return val
		}
	}
	h := sha256.New()
	found := false
	for _, name := range []string{"index.html", "lingo-logo.png", "lingo-icon.png"} {
		fp := filepath.Join(frontendDist, name)
		if data, err := os.ReadFile(fp); err == nil {
			found = true
			h.Write([]byte(name))
			h.Write([]byte{0})
			h.Write(data)
			h.Write([]byte{0})
		}
	}
	if !found {
		return ""
	}
	return hex.EncodeToString(h.Sum(nil))[:12]
}

func sendNativeGUICmd(sockPath, cmd string, timeout time.Duration) (string, error) {
	conn, err := net.DialTimeout("unix", sockPath, timeout)
	if err != nil {
		return "", err
	}
	defer conn.Close()
	_ = conn.SetDeadline(time.Now().Add(timeout))
	if _, err := conn.Write([]byte(cmd + "\n")); err != nil {
		return "", err
	}
	buf := make([]byte, 512)
	n, err := conn.Read(buf)
	if err != nil && err != io.EOF {
		return "", err
	}
	return strings.TrimSpace(string(buf[:n])), nil
}

func tryRaiseNativeGUI(sockPath, expectedFrontendDist, expectedBuild string, timeout time.Duration, log *logger) bool {
	if _, err := os.Stat(sockPath); err != nil {
		return false
	}

	statusRaw, err := sendNativeGUICmd(sockPath, "STATUS", timeout)
	if err != nil {
		if log != nil {
			log.Printf("stale native_gui.sock (%v), cleaning up", err)
		}
		_ = os.Remove(sockPath)
		return false
	}

	var statusObj struct {
		Running      bool   `json:"running"`
		FrontendDist string `json:"frontend_dist"`
		Build        string `json:"build"`
	}
	versionMatches := false
	if json.Unmarshal([]byte(statusRaw), &statusObj) == nil {
		distMatch := expectedFrontendDist == "" || filepath.Clean(statusObj.FrontendDist) == filepath.Clean(expectedFrontendDist)
		buildMatch := expectedBuild == "" || statusObj.Build == expectedBuild
		versionMatches = statusObj.FrontendDist != "" && distMatch && buildMatch
	}

	if !versionMatches {
		if log != nil {
			log.Printf("running native GUI is an older version (dist=%q build=%q vs expected dist=%q build=%q); retiring it before launch", statusObj.FrontendDist, statusObj.Build, expectedFrontendDist, expectedBuild)
		}
		_, _ = sendNativeGUICmd(sockPath, "QUIT", timeout)
		if runtime.GOOS == "darwin" {
			_ = exec.Command("/bin/launchctl", "bootout", "gui/"+strconv.Itoa(os.Getuid())+"/"+nativeGuiLabel).Run()
		}
		deadline := time.Now().Add(3 * time.Second)
		for time.Now().Before(deadline) {
			if _, serr := os.Stat(sockPath); os.IsNotExist(serr) {
				break
			}
			conn, derr := net.DialTimeout("unix", sockPath, 150*time.Millisecond)
			if derr != nil {
				_ = os.Remove(sockPath)
				break
			}
			_ = conn.Close()
			time.Sleep(120 * time.Millisecond)
		}
		return false
	}

	resp, err := sendNativeGUICmd(sockPath, "RAISE", timeout)
	if err != nil {
		return false
	}
	return strings.Contains(resp, "OK")
}

func waitForNativeGUISock(sockPath string, timeout time.Duration, log *logger) bool {
	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		conn, err := net.DialTimeout("unix", sockPath, 400*time.Millisecond)
		if err == nil {
			_ = conn.SetDeadline(time.Now().Add(500 * time.Millisecond))
			_, _ = conn.Write([]byte("STATUS\n"))
			buf := make([]byte, 128)
			n, _ := conn.Read(buf)
			_ = conn.Close()
			if n > 0 {
				log.Printf("native desktop GUI ready via socket %s", sockPath)
				return true
			}
		}
		time.Sleep(150 * time.Millisecond)
	}
	return false
}

var swiftVersionRe = regexp.MustCompile(`(?i)Swift version\s+(\d+)\.(\d+)`)

func parseSwiftVersionAtLeast(output string, minMajor, minMinor int) bool {
	m := swiftVersionRe.FindStringSubmatch(output)
	if len(m) < 3 {
		return false
	}
	major, err1 := strconv.Atoi(m[1])
	minor, err2 := strconv.Atoi(m[2])
	if err1 != nil || err2 != nil {
		return false
	}
	if major != minMajor {
		return major > minMajor
	}
	return minor >= minMinor
}

func normalizeSwiftVersionLine(output string) string {
	for _, line := range strings.Split(output, "\n") {
		fields := strings.Fields(line)
		if len(fields) > 0 {
			return strings.Join(fields, " ")
		}
	}
	return ""
}

func hasWorkingSwiftToolchain(log *logger) (bool, string) {
	if runtime.GOOS != "darwin" {
		return false, ""
	}
	if err := exec.Command("/usr/bin/xcode-select", "-p").Run(); err != nil {
		log.Printf("xcode-select -p unavailable (%v); skipping on-device SwiftUI compile", err)
		return false, ""
	}
	out, err := exec.Command("/usr/bin/swift", "--version").CombinedOutput()
	if err != nil {
		log.Printf("swift --version failed (%v); skipping on-device SwiftUI compile", err)
		return false, ""
	}
	text := string(out)
	norm := normalizeSwiftVersionLine(text)
	if !parseSwiftVersionAtLeast(text, 5, 9) {
		log.Printf("swift toolchain version below 5.9 (%s); skipping on-device SwiftUI compile", norm)
		return false, ""
	}
	return true, norm
}

func readSwiftSourceShortHash(resourcesDir string) string {
	hashRaw, err := os.ReadFile(filepath.Join(resourcesDir, "swift_source.sha256"))
	if err != nil {
		return ""
	}
	hash := strings.TrimSpace(string(hashRaw))
	if len(hash) < 8 {
		return ""
	}
	return hash[:8]
}

func resolveCachedSwiftUIApp(appSupport, resourcesDir string) string {
	short := readSwiftSourceShortHash(resourcesDir)
	if short == "" {
		return ""
	}
	appBundle := filepath.Join(appSupport, "swift-apps", "Lingo-"+short+".app")
	bin := filepath.Join(appBundle, "Contents", "MacOS", "LingoReelApp")
	if isExecutableFile(bin) {
		return appBundle
	}
	return ""
}

func swiftBuildPreviouslyFailed(appSupport, resourcesDir, swiftVerLine string) bool {
	short := readSwiftSourceShortHash(resourcesDir)
	if short == "" {
		return false
	}
	markerPath := filepath.Join(appSupport, "swift-apps", "failed_build.marker")
	raw, err := os.ReadFile(markerPath)
	if err != nil {
		return false
	}
	expected := short + "|" + strings.TrimSpace(swiftVerLine)
	return strings.TrimSpace(string(raw)) == expected
}

func testPyQt6Candidate(pyPath string, log *logger) bool {
	if !isExecutableFile(pyPath) {
		return false
	}
	cmd := exec.Command(pyPath, "-B", "-c", "import PyQt6.QtWidgets")
	err := cmd.Run()
	if err == nil {
		log.Printf("PyQt6 available in: %s", pyPath)
		return true
	}
	log.Printf("PyQt6 not available in %s (%v)", pyPath, err)
	return false
}

func httpCheckConsole(baseURL string, timeout time.Duration) bool {
	u := strings.TrimRight(strings.TrimSpace(baseURL), "/")
	if u == "" {
		return false
	}
	client := &http.Client{Timeout: timeout}
	resp, err := client.Get(u + "/console/api/state")
	if err != nil {
		return false
	}
	defer resp.Body.Close()
	_, _ = io.Copy(io.Discard, io.LimitReader(resp.Body, 4096))
	return resp.StatusCode >= 200 && resp.StatusCode < 300
}

func openURL(url string, log *logger) {
	if runtime.GOOS == "darwin" {
		cmd := exec.Command("/usr/bin/open", url)
		if out, err := cmd.CombinedOutput(); err != nil {
			log.Printf("open %s failed: %v (%s)", url, err, strings.TrimSpace(string(out)))
		} else {
			log.Printf("opened URL via /usr/bin/open: %s", url)
		}
		return
	}
	if opener, err := exec.LookPath("xdg-open"); err == nil {
		_ = exec.Command(opener, url).Start()
	}
}

func showAlert(title, message string, log *logger) {
	log.Printf("ALERT %s: %s", title, message)
	if runtime.GOOS != "darwin" {
		fmt.Fprintf(os.Stderr, "%s: %s\n", title, message)
		return
	}
	cmd := exec.Command(
		"/usr/bin/osascript",
		"-e", "on run argv",
		"-e", "display alert (item 1 of argv) message (item 2 of argv) as warning",
		"-e", "end run",
		title,
		message,
	)
	_ = cmd.Run()
}

func isExecutableFile(p string) bool {
	info, err := os.Stat(p)
	if err != nil || info.IsDir() {
		return false
	}
	return info.Mode().Perm()&0o111 != 0
}

func testPythonCandidate(pyPath string, log *logger) bool {
	if !isExecutableFile(pyPath) {
		return false
	}
	cmd := exec.Command(pyPath, "-B", "-c", "import sys, http.server, sqlite3; assert sys.version_info >= (3, 9)")
	err := cmd.Run()
	if err == nil {
		log.Printf("python candidate OK: %s", pyPath)
		return true
	}
	log.Printf("python candidate rejected: %s (%v)", pyPath, err)
	return false
}

func findWorkingPython(venvDir, homeDir string, log *logger) string {
	candidates := []string{
		filepath.Join(venvDir, "bin", "python"),
		filepath.Join(venvDir, "bin", "python3"),
		"/opt/homebrew/opt/python@3.12/bin/python3.12",
		"/opt/homebrew/bin/python3.12",
		"/opt/homebrew/bin/python3.11",
		"/opt/homebrew/bin/python3.10",
		"/opt/homebrew/bin/python3",
		"/usr/local/opt/python@3.12/bin/python3.12",
		"/usr/local/bin/python3.12",
		"/usr/local/bin/python3.11",
		"/usr/local/bin/python3.10",
		"/usr/local/bin/python3",
		"/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12",
		"/Library/Frameworks/Python.framework/Versions/3.11/bin/python3.11",
		"/Library/Frameworks/Python.framework/Versions/3.10/bin/python3.10",
		"/Library/Frameworks/Python.framework/Versions/Current/bin/python3",
		filepath.Join(homeDir, ".pyenv", "shims", "python3"),
		filepath.Join(homeDir, "miniconda3", "bin", "python3"),
		filepath.Join(homeDir, "anaconda3", "bin", "python3"),
		filepath.Join(homeDir, "miniforge3", "bin", "python3"),
	}

	for _, pattern := range []string{
		filepath.Join(filepath.Dir(venvDir), "python", "*", "bin", "python3*"),
		"/opt/homebrew/opt/python@*/bin/python3*",
		"/usr/local/opt/python@*/bin/python3*",
		"/Library/Frameworks/Python.framework/Versions/*/bin/python3",
	} {
		if matches, err := filepath.Glob(pattern); err == nil {
			sort.Strings(matches)
			candidates = append(candidates, matches...)
		}
	}

	for _, name := range []string{"python3.12", "python3.11", "python3.10", "python3"} {
		if p, err := exec.LookPath(name); err == nil {
			if runtime.GOOS == "darwin" && p == "/usr/bin/python3" {
				continue
			}
			candidates = append(candidates, p)
		}
	}

	seen := map[string]bool{}
	for _, cand := range candidates {
		if cand == "" || seen[cand] {
			continue
		}
		seen[cand] = true
		if testPythonCandidate(cand, log) {
			return cand
		}
	}

	if runtime.GOOS == "darwin" && isExecutableFile("/usr/bin/python3") {
		if err := exec.Command("/usr/bin/xcode-select", "-p").Run(); err == nil {
			if testPythonCandidate("/usr/bin/python3", log) {
				return "/usr/bin/python3"
			}
		} else {
			log.Printf("skipping /usr/bin/python3 because xcode-select -p is not configured")
		}
	}

	return ""
}

func xmlEscape(s string) string {
	var buf bytes.Buffer
	_ = xml.EscapeText(&buf, []byte(s))
	return buf.String()
}

func buildLaunchdPlistWithLabel(label, pythonBin, scriptPath, workDir, logPath string, envMap map[string]string) string {
	keys := make([]string, 0, len(envMap))
	for k := range envMap {
		keys = append(keys, k)
	}
	sort.Strings(keys)

	var b strings.Builder
	b.WriteString(`<?xml version="1.0" encoding="UTF-8"?>` + "\n")
	b.WriteString(`<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">` + "\n")
	b.WriteString(`<plist version="1.0">` + "\n<dict>\n")
	b.WriteString("  <key>Label</key>\n  <string>" + xmlEscape(label) + "</string>\n")
	b.WriteString("  <key>ProgramArguments</key>\n  <array>\n")
	b.WriteString("    <string>" + xmlEscape(pythonBin) + "</string>\n")
	b.WriteString("    <string>-B</string>\n")
	b.WriteString("    <string>" + xmlEscape(scriptPath) + "</string>\n")
	b.WriteString("  </array>\n")
	b.WriteString("  <key>WorkingDirectory</key>\n  <string>" + xmlEscape(workDir) + "</string>\n")
	b.WriteString("  <key>EnvironmentVariables</key>\n  <dict>\n")
	for _, k := range keys {
		b.WriteString("    <key>" + xmlEscape(k) + "</key>\n    <string>" + xmlEscape(envMap[k]) + "</string>\n")
	}
	b.WriteString("  </dict>\n")
	b.WriteString("  <key>StandardOutPath</key>\n  <string>" + xmlEscape(logPath) + "</string>\n")
	b.WriteString("  <key>StandardErrorPath</key>\n  <string>" + xmlEscape(logPath) + "</string>\n")
	b.WriteString("  <key>LimitLoadToSessionType</key>\n  <string>Aqua</string>\n")
	b.WriteString("  <key>RunAtLoad</key>\n  <true/>\n")
	b.WriteString("  <key>KeepAlive</key>\n  <false/>\n")
	b.WriteString("  <key>ProcessType</key>\n  <string>Interactive</string>\n")
	b.WriteString("  <key>AbandonProcessGroup</key>\n  <true/>\n")
	b.WriteString("</dict>\n</plist>\n")
	return b.String()
}

func buildLaunchdPlist(pythonBin, scriptPath, workDir, logPath string, envMap map[string]string) string {
	return buildLaunchdPlistWithLabel(consoleLabel, pythonBin, scriptPath, workDir, logPath, envMap)
}

func waitForConsoleURL(consoleURLFile string, timeout time.Duration, log *logger) string {
	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		raw, err := os.ReadFile(consoleURLFile)
		if err == nil {
			u := strings.TrimSpace(string(raw))
			if u != "" && httpCheckConsole(u, 800*time.Millisecond) {
				log.Printf("console became healthy at %s", u)
				return u
			}
		}
		time.Sleep(150 * time.Millisecond)
	}
	return ""
}

func launchViaLaunchd(label, plistPath string, log *logger) bool {
	if runtime.GOOS != "darwin" {
		return false
	}
	uid := strconv.Itoa(os.Getuid())
	domain := "gui/" + uid
	target := domain + "/" + label

	_ = exec.Command("/bin/launchctl", "bootout", target).Run()
	_ = exec.Command("/bin/launchctl", "bootout", domain, plistPath).Run()
	time.Sleep(120 * time.Millisecond)

	bootCmd := exec.Command("/bin/launchctl", "bootstrap", domain, plistPath)
	if out, err := bootCmd.CombinedOutput(); err != nil {
		log.Printf("launchctl bootstrap failed for %s: %v (%s)", label, err, strings.TrimSpace(string(out)))
		return false
	}
	log.Printf("launchctl bootstrap succeeded for %s", target)

	kickCmd := exec.Command("/bin/launchctl", "kickstart", target)
	if out, err := kickCmd.CombinedOutput(); err != nil {
		log.Printf("launchctl kickstart note: %v (%s)", err, strings.TrimSpace(string(out)))
	} else {
		log.Printf("launchctl kickstart succeeded for %s", target)
	}
	return true
}

var errSetupAlreadyRunning = errors.New("setup already running")

func isProcessAlive(pid int) bool {
	if pid <= 0 {
		return false
	}
	return syscall.Kill(pid, 0) == nil
}

func acquireSetupLock(lockPath string) (bool, int) {
	pidBytes := []byte(strconv.Itoa(os.Getpid()) + "\n")
	for attempt := 0; attempt < 2; attempt++ {
		f, err := os.OpenFile(lockPath, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0o644)
		if err == nil {
			_, _ = f.Write(pidBytes)
			_ = f.Close()
			return true, 0
		}
		if !os.IsExist(err) {
			return true, 0
		}
		raw, rerr := os.ReadFile(lockPath)
		if rerr == nil {
			if pid, perr := strconv.Atoi(strings.TrimSpace(string(raw))); perr == nil && isProcessAlive(pid) {
				return false, pid
			}
		}
		// Stale or unreadable lock file from a dead process: remove and retry atomic O_EXCL create once
		_ = os.Remove(lockPath)
	}
	return false, 0
}

func writeSetupStatusAtomic(statusPath, title, detail string) {
	content := strings.TrimSpace(title) + "\n" + strings.TrimSpace(detail) + "\n"
	tmp := statusPath + ".tmp"
	if err := os.WriteFile(tmp, []byte(content), 0o644); err == nil {
		_ = os.Rename(tmp, statusPath)
	}
}

func extractSetupStatusDetail(line string) string {
	s := strings.TrimSpace(line)
	if s == "" {
		return ""
	}
	if strings.HasPrefix(s, "[Lingo] ") {
		return strings.TrimSpace(strings.TrimPrefix(s, "[Lingo] "))
	}
	lower := strings.ToLower(s)
	switch {
	case strings.Contains(lower, "pyqt6") && (strings.Contains(lower, "downloading") || strings.Contains(lower, "downloaded")):
		return "正在下载 macOS 原生桌面组件（PyQt6）..."
	case strings.Contains(lower, "installing collected packages") || strings.Contains(lower, "installed ") && strings.Contains(lower, " package"):
		return "正在安装核心依赖组件..."
	case strings.Contains(lower, "compiling ") && strings.Contains(lower, "lingoreel"):
		return "正在编译原生 SwiftUI 桌面界面..."
	case strings.Contains(lower, "linking ") && strings.Contains(lower, "lingoreel"):
		return "正在链接原生 SwiftUI 可执行文件..."
	case strings.Contains(lower, "downloading cpython") || (strings.Contains(lower, "downloading") && strings.Contains(lower, "python")):
		return "正在下载独立版 Python 3.12 运行时..."
	default:
		return ""
	}
}

func showNotification(title, message string, log *logger) {
	if runtime.GOOS != "darwin" {
		return
	}
	cmd := exec.Command(
		"/usr/bin/osascript",
		"-e", "on run argv",
		"-e", "display notification (item 2 of argv) with title (item 1 of argv)",
		"-e", "end run",
		title,
		message,
	)
	if err := cmd.Run(); err != nil && log != nil {
		log.Printf("notification note: %v", err)
	}
}

func startNativeProgressHUD(appSupport, resourcesDir, statusPath, raisePath, title, detail string, log *logger) *exec.Cmd {
	if runtime.GOOS != "darwin" {
		return nil
	}
	jxaPath := filepath.Join(resourcesDir, "setup_progress.jxa")
	if _, err := os.Stat(jxaPath); err != nil {
		showNotification(title, detail, log)
		return nil
	}
	logoPath := filepath.Join(resourcesDir, "lingo-logo.png")
	cmd := exec.Command("/usr/bin/osascript", "-l", "JavaScript", jxaPath, statusPath, raisePath, logoPath, title, detail)
	var hudLog *os.File
	if f, err := os.OpenFile(filepath.Join(appSupport, "setup_hud.log"), os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0o644); err == nil {
		hudLog = f
		cmd.Stdout = hudLog
		cmd.Stderr = hudLog
	}
	err := cmd.Start()
	if hudLog != nil {
		_ = hudLog.Close()
	}
	if err != nil {
		log.Printf("failed to start native setup HUD (%v); falling back to macOS notification", err)
		showNotification(title, detail, log)
		return nil
	}
	log.Printf("started native Cocoa setup progress HUD (pid=%d)", cmd.Process.Pid)
	return cmd
}

func stopNativeProgressHUD(statusPath string, hudCmd *exec.Cmd, log *logger) {
	writeSetupStatusAtomic(statusPath, "DONE", "")
	_ = os.Remove(statusPath)
	if hudCmd == nil || hudCmd.Process == nil {
		return
	}
	done := make(chan error, 1)
	go func() { done <- hudCmd.Wait() }()
	select {
	case <-done:
		log.Printf("native setup HUD closed cleanly")
	case <-time.After(900 * time.Millisecond):
		_ = hudCmd.Process.Signal(syscall.SIGTERM)
		select {
		case <-done:
		case <-time.After(400 * time.Millisecond):
			_ = hudCmd.Process.Kill()
			<-done
		}
		log.Printf("native setup HUD terminated after timeout")
	}
}

func runNativeSetupHeadless(appSupport, resourcesDir, modeFlag string, log *logger) error {
	lockPath := filepath.Join(appSupport, "setup.lock")
	statusPath := filepath.Join(appSupport, "setup_status.txt")
	raisePath := filepath.Join(appSupport, "setup_raise.flag")
	setupLogPath := filepath.Join(appSupport, "setup.log")

	acquired, existingPID := acquireSetupLock(lockPath)
	if !acquired {
		log.Printf("setup already running (pid=%d); signaling progress HUD to come to front", existingPID)
		_ = os.WriteFile(raisePath, []byte("RAISE\n"), 0o644)
		return errSetupAlreadyRunning
	}
	defer os.Remove(lockPath)
	defer os.Remove(raisePath)

	title := "正在首次准备 Lingo 原生桌面端..."
	detail := "正在自动检测并安装 Python 3.12 与原生桌面组件，请稍候..."
	if modeFlag == "--swift-build" {
		title = "正在为您准备 100% 原生 SwiftUI 桌面端..."
		detail = "首次启动本机编译约需 15–30 秒，完成后将自动秒开..."
	}

	writeSetupStatusAtomic(statusPath, title, detail)
	hudCmd := startNativeProgressHUD(appSupport, resourcesDir, statusPath, raisePath, title, detail, log)
	defer func() {
		stopNativeProgressHUD(statusPath, hudCmd, log)
	}()

	bootstrapSh := filepath.Join(resourcesDir, "bootstrap.sh")
	if _, err := os.Stat(bootstrapSh); err != nil {
		return fmt.Errorf("未找到初始化脚本：%s", bootstrapSh)
	}

	logFile, err := os.OpenFile(setupLogPath, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0o644)
	if err == nil {
		defer logFile.Close()
		_, _ = fmt.Fprintf(logFile, "=== Lingo Native Setup (%s, mode=%s) ===\n", time.Now().Format("2006-01-02 15:04:05"), modeFlag)
	}

	pr, pw, err := os.Pipe()
	if err != nil {
		return err
	}

	cmd := exec.Command("/bin/bash", bootstrapSh, resourcesDir, "8000", modeFlag)
	cmd.Stdin = nil
	cmd.Stdout = pw
	cmd.Stderr = pw
	cmd.Env = mergeEnv(map[string]string{
		"LINGOREEL_NO_TTY":        "1",
		"LINGOREEL_SKIP_RELAUNCH": "1",
		"LINGOREEL_APP_SUPPORT":   appSupport,
	})

	if err := cmd.Start(); err != nil {
		_ = pr.Close()
		_ = pw.Close()
		return err
	}
	_ = pw.Close()

	scanner := bufio.NewScanner(pr)
	scanner.Buffer(make([]byte, 0, 64*1024), 512*1024)
	for scanner.Scan() {
		line := scanner.Text()
		if logFile != nil {
			_, _ = fmt.Fprintln(logFile, line)
		}
		if step := extractSetupStatusDetail(line); step != "" {
			if strings.Contains(step, "PyQt6") && modeFlag == "--swift-build" {
				title = "正在为您准备同款玩味 3D 原生桌面端..."
			}
			writeSetupStatusAtomic(statusPath, title, step)
		}
	}
	_ = pr.Close()

	waitErr := cmd.Wait()
	if waitErr != nil {
		log.Printf("headless bootstrap (%s) failed: %v", modeFlag, waitErr)
		return waitErr
	}
	writeSetupStatusAtomic(statusPath, "准备完成，正在打开 Lingo...", "正在启动原生桌面控制台窗口...")
	log.Printf("headless bootstrap (%s) completed successfully", modeFlag)
	return nil
}

func launchNativePyQtGUI(venvPy, nativeGuiScript, backendDir, appSupport, consoleLogPath, nativeSockPath string, envMap map[string]string, log *logger) {
	_ = os.WriteFile(consoleLogPath, []byte(fmt.Sprintf("=== Lingo Native Desktop GUI Launch (%s) ===\n", time.Now().Format("2006-01-02 15:04:05"))), 0o644)

	if runtime.GOOS == "darwin" {
		plistPath := filepath.Join(appSupport, nativeGuiLabel+".plist")
		plistContent := buildLaunchdPlistWithLabel(nativeGuiLabel, venvPy, nativeGuiScript, backendDir, consoleLogPath, envMap)
		if err := os.WriteFile(plistPath, []byte(plistContent), 0o644); err == nil {
			if launchViaLaunchd(nativeGuiLabel, plistPath, log) {
				if waitForNativeGUISock(nativeSockPath, 14*time.Second, log) {
					return
				}
				log.Printf("launchd native GUI did not bind socket in 14s; falling back to supervised direct run")
				_ = exec.Command("/bin/launchctl", "bootout", "gui/"+strconv.Itoa(os.Getuid())+"/"+nativeGuiLabel).Run()
			}
		}
	}

	// Supervised direct native GUI launch
	log.Printf("launching desktop_native_gui.py directly (supervised): %s %s", venvPy, nativeGuiScript)
	logFile, _ := os.OpenFile(consoleLogPath, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o644)
	if logFile != nil {
		defer logFile.Close()
	}
	cmd := exec.Command(venvPy, "-B", nativeGuiScript)
	cmd.Dir = backendDir
	cmd.Env = mergeEnv(envMap)
	if logFile != nil {
		cmd.Stdout = logFile
		cmd.Stderr = logFile
	}
	if err := cmd.Start(); err != nil {
		showAlert("Lingo 原生桌面控制台启动失败", fmt.Sprintf("无法启动桌面窗口：%v\n\n日志路径：%s", err, consoleLogPath), log)
		os.Exit(1)
	}
	sigCh := make(chan os.Signal, 2)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)
	go func() {
		sig := <-sigCh
		log.Printf("forwarding signal %v to native GUI pid=%d", sig, cmd.Process.Pid)
		_ = cmd.Process.Signal(syscall.SIGTERM)
	}()
	if err := cmd.Wait(); err != nil {
		log.Printf("desktop_native_gui.py exited with error: %v", err)
	}
}

func launchFirstSetupTerminal(appSupport, resourcesDir, modeFlag string, log *logger) error {
	helperPath := filepath.Join(appSupport, "first_setup.command")
	bootstrapSh := filepath.Join(resourcesDir, "bootstrap.sh")
	quotedRes := "'" + strings.ReplaceAll(resourcesDir, "'", `'\''`) + "'"
	quotedBoot := "'" + strings.ReplaceAll(bootstrapSh, "'", `'\''`) + "'"
	script := fmt.Sprintf("#!/bin/bash\nset -e\nexport LINGOREEL_AUTO_CLOSE_TERMINAL=1\nexec %s %s 8000 %s\n", quotedBoot, quotedRes, modeFlag)
	if err := os.WriteFile(helperPath, []byte(script), 0o755); err != nil {
		return err
	}
	if runtime.GOOS == "darwin" {
		// Clear any inherited quarantine attribute so Terminal runs helper cleanly
		_ = exec.Command("/usr/bin/xattr", "-d", "com.apple.quarantine", helperPath).Run()
		cmd := exec.Command("/usr/bin/open", "-a", "Terminal", helperPath)
		out, err := cmd.CombinedOutput()
		if err != nil {
			log.Printf("open -a Terminal failed: %v (%s)", err, strings.TrimSpace(string(out)))
			return err
		}
		log.Printf("launched first_setup.command (%s) in Terminal via /usr/bin/open", modeFlag)
		return nil
	}
	return fmt.Errorf("terminal bootstrap unsupported on %s", runtime.GOOS)
}

func tailFile(path string, maxLines int) string {
	raw, err := os.ReadFile(path)
	if err != nil {
		return ""
	}
	lines := strings.Split(strings.TrimSpace(string(raw)), "\n")
	if len(lines) > maxLines {
		lines = lines[len(lines)-maxLines:]
	}
	return strings.Join(lines, "\n")
}

func mergeEnv(envMap map[string]string) []string {
	mergedEnv := map[string]string{}
	for _, kv := range os.Environ() {
		if idx := strings.IndexByte(kv, '='); idx > 0 {
			mergedEnv[kv[:idx]] = kv[idx+1:]
		}
	}
	for k, v := range envMap {
		mergedEnv[k] = v
	}
	envSlice := make([]string, 0, len(mergedEnv))
	for k, v := range mergedEnv {
		envSlice = append(envSlice, k+"="+v)
	}
	return envSlice
}

func main() {
	forceWebConsole := false
	forceTerminalSetup := os.Getenv("LINGOREEL_USE_TERMINAL") == "1"
	for _, arg := range os.Args[1:] {
		if arg == "--web-console" {
			forceWebConsole = true
		} else if arg == "--terminal-setup" {
			forceTerminalSetup = true
		}
	}

	homeDir, err := os.UserHomeDir()
	if err != nil || homeDir == "" {
		homeDir = os.Getenv("HOME")
	}

	appSupport := os.Getenv("LINGOREEL_APP_SUPPORT")
	if appSupport == "" {
		if runtime.GOOS == "darwin" {
			appSupport = filepath.Join(homeDir, "Library", "Application Support", "LingoReelStudio")
		} else {
			appSupport = filepath.Join(homeDir, ".lingoreel-studio")
		}
	}

	dataDir := os.Getenv("LINGOREEL_DATA_DIR")
	if dataDir == "" {
		dataDir = filepath.Join(appSupport, "data")
	}
	venvDir := os.Getenv("LINGOREEL_VENV_DIR")
	if venvDir == "" {
		venvDir = filepath.Join(appSupport, ".venv")
	}

	for _, d := range []string{
		dataDir,
		filepath.Join(appSupport, "whisper-cache"),
		filepath.Join(appSupport, "python"),
		filepath.Join(appSupport, "uv-cache"),
		filepath.Join(appSupport, "bin"),
		filepath.Join(appSupport, "swift-apps"),
	} {
		_ = os.MkdirAll(d, 0o755)
	}

	log := newLogger(filepath.Join(appSupport, "launcher.log"))
	defer log.Close()

	exePath, _ := os.Executable()
	if resolved, rerr := filepath.EvalSymlinks(exePath); rerr == nil {
		exePath = resolved
	}
	log.Printf("=== Lingo launcher start (pid=%d, os=%s, arch=%s, exe=%s) ===", os.Getpid(), runtime.GOOS, runtime.GOARCH, exePath)

	resourcesDir := os.Getenv("LINGOREEL_RESOURCES_DIR")
	if resourcesDir == "" {
		contentsDir := filepath.Dir(filepath.Dir(exePath))
		resourcesDir = filepath.Join(contentsDir, "Resources")
	}
	backendDir := filepath.Join(resourcesDir, "backend")
	nativeGuiScript := filepath.Join(backendDir, "desktop_native_gui.py")
	consoleScript := filepath.Join(backendDir, "desktop_console.py")
	frontendDist := filepath.Join(resourcesDir, "frontend", "dist")
	nativeSockPath := filepath.Join(dataDir, "native_gui.sock")
	consoleURLFile := filepath.Join(dataDir, "console_url.txt")
	consoleLogPath := filepath.Join(appSupport, "console.log")
	setupLogPath := filepath.Join(appSupport, "setup.log")

	// Clean up any legacy v1.1.1 browser-based web console agent so it never steals launch
	if !forceWebConsole {
		bootoutLegacyWebConsole(log)
		_ = os.Remove(consoleURLFile)
	}

	// 0a. If standalone precompiled native SwiftUI binary is bundled alongside, exec straight into it
	swiftBin := filepath.Join(filepath.Dir(exePath), "LingoSwiftUI")
	if !forceWebConsole && isExecutableFile(swiftBin) {
		log.Printf("launching bundled native SwiftUI binary: %s", swiftBin)
		_ = syscall.Exec(swiftBin, append([]string{swiftBin}, os.Args[1:]...), os.Environ())
	}

	// 0b. If on-device compiled native SwiftUI Lingo.app is already cached for this release, launch it immediately!
	if !forceWebConsole && runtime.GOOS == "darwin" {
		if cachedSwiftApp := resolveCachedSwiftUIApp(appSupport, resourcesDir); cachedSwiftApp != "" {
			log.Printf("launching cached 100%% native SwiftUI app: %s", cachedSwiftApp)
			cmd := exec.Command("/usr/bin/open", "-a", cachedSwiftApp)
			if out, err := cmd.CombinedOutput(); err == nil {
				return
			} else {
				log.Printf("open cached SwiftUI app failed: %v (%s)", err, strings.TrimSpace(string(out)))
			}
		}

		// 0c. First launch on a Mac with Xcode / Command Line Tools (Swift >= 5.9): build 100% native SwiftUI silently (zero Terminal!)
		if os.Getenv("LINGOREEL_SKIP_SWIFT_BUILD") != "1" {
			pkgSwift := filepath.Join(resourcesDir, "native-app", "Package.swift")
			if _, serr := os.Stat(pkgSwift); serr == nil {
				if ok, swiftVer := hasWorkingSwiftToolchain(log); ok {
					if swiftBuildPreviouslyFailed(appSupport, resourcesDir, swiftVer) {
						log.Printf("previous SwiftUI build failed for current hash & toolchain (%s); skipping auto-build and opening native PyQt6 console", swiftVer)
					} else if forceTerminalSetup {
						log.Printf("Swift toolchain detected (%s); launching Terminal build wizard (--terminal-setup)", swiftVer)
						if err := launchFirstSetupTerminal(appSupport, resourcesDir, "--swift-build", log); err == nil {
							return
						}
					} else {
						log.Printf("Swift toolchain detected (%s); running headless native SwiftUI build with progress HUD (no Terminal)", swiftVer)
						setupErr := runNativeSetupHeadless(appSupport, resourcesDir, "--swift-build", log)
						if errors.Is(setupErr, errSetupAlreadyRunning) {
							return
						}
						if cachedSwiftApp := resolveCachedSwiftUIApp(appSupport, resourcesDir); cachedSwiftApp != "" {
							log.Printf("opening newly built 100%% native SwiftUI app: %s", cachedSwiftApp)
							if out, oerr := exec.Command("/usr/bin/open", "-a", cachedSwiftApp).CombinedOutput(); oerr == nil {
								return
							} else {
								log.Printf("open newly built SwiftUI app failed: %v (%s)", oerr, strings.TrimSpace(string(out)))
							}
						}
						if setupErr != nil {
							tail := tailFile(setupLogPath, 10)
							showAlert(
								"Lingo 首次环境准备未完成",
								fmt.Sprintf("自动准备原生桌面端时遇到错误（%v）。\n\n日志路径：%s\n\n最近日志：\n%s", setupErr, setupLogPath, tail),
								log,
							)
							os.Exit(1)
						}
						// If Swift build fell back cleanly to PyQt6 setup inside bootstrap.sh, proceed directly to Step 2!
					}
				}
			}
		}
	}

	// 1. If Native PyQt6 Desktop Console GUI (same version/build) is already running, bring its native window to front!
	//    If an older version is running in the menu bar, tryRaiseNativeGUI retires it cleanly first.
	expectedBuildID := computeFrontendBuildID(frontendDist)
	if !forceWebConsole && tryRaiseNativeGUI(nativeSockPath, frontendDist, expectedBuildID, 1*time.Second, log) {
		log.Printf("raised existing native desktop GUI via %s (build=%s)", nativeSockPath, expectedBuildID)
		return
	}

	// Build rich PATH so Homebrew / Python.org / uv / venv binaries are always visible under LaunchServices
	basePath := strings.Join([]string{
		filepath.Join(venvDir, "bin"),
		filepath.Join(appSupport, "bin"),
		"/opt/homebrew/bin",
		"/opt/homebrew/opt/python@3.12/bin",
		"/usr/local/bin",
		"/usr/local/opt/python@3.12/bin",
		"/Library/Frameworks/Python.framework/Versions/3.12/bin",
		"/usr/bin",
		"/bin",
		"/usr/sbin",
		"/sbin",
		os.Getenv("PATH"),
	}, ":")
	_ = os.Setenv("PATH", basePath)

	hfEndpoint := os.Getenv("HF_ENDPOINT")
	if hfEndpoint == "" {
		hfEndpoint = "https://hf-mirror.com"
	}

	envMap := map[string]string{
		"HOME":                    homeDir,
		"PATH":                    basePath,
		"LINGOREEL_DATA_DIR":      dataDir,
		"LINGOREEL_FRONTEND_DIST": frontendDist,
		"LINGOREEL_VENV_DIR":      venvDir,
		"LINGOREEL_DESKTOP_APP":   "1",
		"HF_HOME":                 filepath.Join(appSupport, "whisper-cache"),
		"HF_ENDPOINT":             hfEndpoint,
		"UV_PYTHON_INSTALL_DIR":   filepath.Join(appSupport, "python"),
		"UV_CACHE_DIR":            filepath.Join(appSupport, "uv-cache"),
		"PYTHONDONTWRITEBYTECODE": "1",
		"PYTHONUNBUFFERED":        "1",
		"LC_ALL":                  "en_US.UTF-8",
		"LANG":                    "en_US.UTF-8",
	}

	// 2. Native Desktop Control Center window (Playful 3D PyQt6 Cocoa — zero browser, zero Terminal!)
	if !forceWebConsole {
		if _, err := os.Stat(nativeGuiScript); err == nil {
			resolveVenvPy := func() string {
				p := filepath.Join(venvDir, "bin", "python")
				if !isExecutableFile(p) {
					p = filepath.Join(venvDir, "bin", "python3")
				}
				return p
			}

			venvPy := resolveVenvPy()
			if testPyQt6Candidate(venvPy, log) {
				launchNativePyQtGUI(venvPy, nativeGuiScript, backendDir, appSupport, consoleLogPath, nativeSockPath, envMap, log)
				return
			}

			// First-time launch on macOS without Xcode CLT: silently install Python/PyQt6 with native Cocoa progress HUD (NO Terminal!)
			if runtime.GOOS == "darwin" && os.Getenv("LINGOREEL_SKIP_NATIVE_SETUP") != "1" {
				if _, berr := os.Stat(filepath.Join(resourcesDir, "bootstrap.sh")); berr == nil {
					if forceTerminalSetup {
						log.Printf("PyQt6 not yet installed in %s; launching Terminal setup wizard (--terminal-setup)", venvDir)
						if err := launchFirstSetupTerminal(appSupport, resourcesDir, "--native-setup", log); err == nil {
							return
						}
					} else {
						log.Printf("PyQt6 not yet installed in %s; running silent headless setup with native progress HUD (no Terminal)", venvDir)
						setupErr := runNativeSetupHeadless(appSupport, resourcesDir, "--native-setup", log)
						if errors.Is(setupErr, errSetupAlreadyRunning) {
							return
						}
						if setupErr == nil {
							venvPy = resolveVenvPy()
							if testPyQt6Candidate(venvPy, log) {
								launchNativePyQtGUI(venvPy, nativeGuiScript, backendDir, appSupport, consoleLogPath, nativeSockPath, envMap, log)
								return
							}
						} else {
							tail := tailFile(setupLogPath, 10)
							showAlert(
								"Lingo 原生桌面组件初始化失败",
								fmt.Sprintf("自动安装 Python 3.12 / PyQt6 时遇到错误（%v），请检查网络连接后重试。\n\n日志路径：%s\n\n最近日志：\n%s", setupErr, setupLogPath, tail),
								log,
							)
							os.Exit(1)
						}
					}
				}
			}

			// Do NOT silently fall back to a browser web page console unless explicitly requested!
			if os.Getenv("LINGOREEL_ALLOW_WEB_CONSOLE") != "1" {
				showAlert(
					"Lingo 需要完成首次原生桌面环境初始化",
					fmt.Sprintf("本机尚未安装 Swift 命令行工具或 PyQt6 桌面组件。\n\n请检查网络连接后重新打开 Lingo，或查看日志：\n%s", setupLogPath),
					log,
				)
				os.Exit(1)
			}
		}
	}

	// 3. Explicit --web-console mode only
	if raw, err := os.ReadFile(consoleURLFile); err == nil {
		existing := strings.TrimSpace(string(raw))
		if existing != "" && httpCheckConsole(existing, 1*time.Second) {
			log.Printf("existing web console is healthy at %s, reopening browser", existing)
			openURL(existing, log)
			return
		}
		_ = os.Remove(consoleURLFile)
	}

	if _, err := os.Stat(consoleScript); err != nil {
		showAlert(
			"Lingo 启动失败",
			fmt.Sprintf("未找到控制台程序文件：%s\n请将「Lingo.app」完整拖入「应用程序」文件夹后重试。", consoleScript),
			log,
		)
		os.Exit(1)
	}

	pythonBin := findWorkingPython(venvDir, homeDir, log)
	if pythonBin == "" {
		log.Printf("no working python3 found; launching first_setup.command in Terminal")
		if err := launchFirstSetupTerminal(appSupport, resourcesDir, "--native-setup", log); err != nil {
			showAlert(
				"Lingo 需要初始化 Python 环境",
				fmt.Sprintf("本机暂未检测到 Python 3，且自动打开终端失败：%v\n\n请打开「终端」运行：\n\"%s\" \"%s\" 8000 --native-setup", err, filepath.Join(resourcesDir, "bootstrap.sh"), resourcesDir),
				log,
			)
			os.Exit(1)
		}
		return
	}

	_ = os.WriteFile(consoleLogPath, []byte(fmt.Sprintf("=== Lingo Console Launch (%s) ===\n", time.Now().Format("2006-01-02 15:04:05"))), 0o644)

	if runtime.GOOS == "darwin" {
		plistPath := filepath.Join(appSupport, consoleLabel+".plist")
		plistContent := buildLaunchdPlist(pythonBin, consoleScript, backendDir, consoleLogPath, envMap)
		if err := os.WriteFile(plistPath, []byte(plistContent), 0o644); err == nil {
			if launchViaLaunchd(consoleLabel, plistPath, log) {
				if url := waitForConsoleURL(consoleURLFile, 6*time.Second, log); url != "" {
					openURL(url, log)
					return
				}
				_ = exec.Command("/bin/launchctl", "bootout", "gui/"+strconv.Itoa(os.Getuid())+"/"+consoleLabel).Run()
				_ = os.Remove(consoleURLFile)
			}
		}
	}

	logFile, _ := os.OpenFile(consoleLogPath, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o644)
	if logFile != nil {
		defer logFile.Close()
	}
	cmd := exec.Command(pythonBin, "-B", consoleScript)
	cmd.Dir = backendDir
	cmd.Env = mergeEnv(envMap)
	if logFile != nil {
		cmd.Stdout = logFile
		cmd.Stderr = logFile
	}
	if err := cmd.Start(); err != nil {
		showAlert("Lingo 启动失败", fmt.Sprintf("无法启动控制台：%v\n\n日志路径：%s", err, consoleLogPath), log)
		os.Exit(1)
	}

	doneCh := make(chan error, 1)
	go func() { doneCh <- cmd.Wait() }()

	sigCh := make(chan os.Signal, 2)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)
	go func() {
		<-sigCh
		_ = cmd.Process.Signal(syscall.SIGTERM)
	}()

	opened := false
	deadline := time.Now().Add(12 * time.Second)
	for time.Now().Before(deadline) {
		select {
		case err := <-doneCh:
			tail := tailFile(consoleLogPath, 10)
			showAlert("Lingo 控制台异常退出", fmt.Sprintf("控制台进程意外终止（%v）。\n\n最近日志：\n%s", err, tail), log)
			os.Exit(1)
		default:
			if raw, rerr := os.ReadFile(consoleURLFile); rerr == nil {
				u := strings.TrimSpace(string(raw))
				if u != "" && httpCheckConsole(u, 800*time.Millisecond) {
					openURL(u, log)
					opened = true
				}
			}
			if opened {
				break
			}
			time.Sleep(150 * time.Millisecond)
		}
		if opened {
			break
		}
	}
	if !opened {
		tail := tailFile(consoleLogPath, 10)
		showAlert("Lingo 控制台启动超时", fmt.Sprintf("控制台未能在 12 秒内就绪。\n\n最近日志：\n%s", tail), log)
		_ = cmd.Process.Signal(syscall.SIGTERM)
		os.Exit(1)
	}
	_ = <-doneCh
}
