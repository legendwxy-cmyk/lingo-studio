package main

import (
	"net"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestBuildLaunchdPlistUTF8AndEscaping(t *testing.T) {
	plist := buildLaunchdPlistWithLabel(
		nativeGuiLabel,
		"/Users/测试用户/Library/Application Support/LingoReelStudio/.venv/bin/python",
		"/Applications/Lingo.app/Contents/Resources/backend/desktop_native_gui.py",
		"/Applications/Lingo.app/Contents/Resources/backend",
		"/Users/测试用户/Library/Application Support/LingoReelStudio/console.log",
		map[string]string{
			"LINGOREEL_DATA_DIR": "/Users/测试用户/Library/Application Support/LingoReelStudio/data",
			"SPECIAL_XML":        "a&b<c>d",
		},
	)

	if !strings.Contains(plist, "<string>com.lingoreel.studio.nativegui</string>") {
		t.Fatalf("missing nativeGuiLabel in plist:\n%s", plist)
	}
	if !strings.Contains(plist, "Lingo.app") {
		t.Fatalf("missing Lingo.app bundle path in plist:\n%s", plist)
	}
	if !strings.Contains(plist, "a&amp;b&lt;c&gt;d") {
		t.Fatalf("XML escaping failed:\n%s", plist)
	}
	if !strings.Contains(plist, "<string>Aqua</string>") {
		t.Fatalf("missing Aqua session type in plist:\n%s", plist)
	}
}

func TestTryRaiseNativeGUISocket(t *testing.T) {
	tmp := t.TempDir()
	sock := filepath.Join(tmp, "native_gui.sock")
	expectedDist := "/Applications/Lingo.app/Contents/Resources/frontend/dist"
	expectedBuild := "abc123def456"

	if tryRaiseNativeGUI(sock, expectedDist, expectedBuild, 300*time.Millisecond, nil) {
		t.Fatalf("expected false for missing socket")
	}

	ln, err := net.Listen("unix", sock)
	if err != nil {
		t.Fatalf("listen unix failed: %v", err)
	}
	defer ln.Close()

	cmds := make(chan string, 2)
	go func() {
		for i := 0; i < 2; i++ {
			conn, aerr := ln.Accept()
			if aerr != nil {
				return
			}
			buf := make([]byte, 64)
			n, _ := conn.Read(buf)
			cmd := strings.TrimSpace(string(buf[:n]))
			cmds <- cmd
			if cmd == "STATUS" {
				_, _ = conn.Write([]byte(`{"running":true,"frontend_dist":"` + expectedDist + `","build":"` + expectedBuild + `"}` + "\n"))
			} else {
				_, _ = conn.Write([]byte("OK\n"))
			}
			_ = conn.Close()
		}
	}()

	if !tryRaiseNativeGUI(sock, expectedDist, expectedBuild, 1*time.Second, nil) {
		t.Fatalf("expected true when live matching-version socket responds OK")
	}
	if got := <-cmds; got != "STATUS" {
		t.Fatalf("expected STATUS first, got %q", got)
	}
	if got := <-cmds; got != "RAISE" {
		t.Fatalf("expected RAISE second, got %q", got)
	}
}

func TestTryRaiseNativeGUIRetiresStaleVersion(t *testing.T) {
	tmp := t.TempDir()
	sock := filepath.Join(tmp, "native_gui.sock")

	ln, err := net.Listen("unix", sock)
	if err != nil {
		t.Fatalf("listen unix failed: %v", err)
	}

	gotQuit := make(chan bool, 1)
	go func() {
		for i := 0; i < 2; i++ {
			conn, aerr := ln.Accept()
			if aerr != nil {
				return
			}
			buf := make([]byte, 64)
			n, _ := conn.Read(buf)
			cmd := strings.TrimSpace(string(buf[:n]))
			if cmd == "STATUS" {
				// Simulate old v1.2.0 GUI with stale frontend_dist / missing build
				_, _ = conn.Write([]byte(`{"running":true}` + "\n"))
				_ = conn.Close()
			} else if cmd == "QUIT" {
				_, _ = conn.Write([]byte("OK\n"))
				_ = conn.Close()
				_ = ln.Close()
				_ = os.Remove(sock)
				gotQuit <- true
				return
			}
		}
	}()

	raised := tryRaiseNativeGUI(sock, "/Applications/Lingo.app/Contents/Resources/frontend/dist", "newbuild1234", 1*time.Second, nil)
	if raised {
		t.Fatalf("expected false when running GUI is an older version")
	}
	select {
	case <-gotQuit:
	case <-time.After(1 * time.Second):
		t.Fatalf("expected launcher to send QUIT to stale native GUI")
	}
}

func TestComputeFrontendBuildID(t *testing.T) {
	tmp := t.TempDir()
	if err := os.WriteFile(filepath.Join(tmp, "index.html"), []byte("<html>Lingo</html>"), 0o644); err != nil {
		t.Fatal(err)
	}
	id1 := computeFrontendBuildID(tmp)
	if len(id1) != 12 {
		t.Fatalf("expected 12-char fallback build id, got %q", id1)
	}
	if err := os.WriteFile(filepath.Join(tmp, ".lingo_build_id"), []byte("deadbeef1234\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	if got := computeFrontendBuildID(tmp); got != "deadbeef1234" {
		t.Fatalf("expected marker build id deadbeef1234, got %q", got)
	}
}

func TestResolveCachedSwiftUIApp(t *testing.T) {
	tmp := t.TempDir()
	resDir := filepath.Join(tmp, "Resources")
	appSupport := filepath.Join(tmp, "Support")
	if err := os.MkdirAll(resDir, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(resDir, "swift_source.sha256"), []byte("abcdef1234567890\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	if got := resolveCachedSwiftUIApp(appSupport, resDir); got != "" {
		t.Fatalf("expected empty when cached app absent, got %q", got)
	}

	cachedBinDir := filepath.Join(appSupport, "swift-apps", "Lingo-abcdef12.app", "Contents", "MacOS")
	if err := os.MkdirAll(cachedBinDir, 0o755); err != nil {
		t.Fatal(err)
	}
	binPath := filepath.Join(cachedBinDir, "LingoReelApp")
	if err := os.WriteFile(binPath, []byte("#!/bin/sh\n"), 0o755); err != nil {
		t.Fatal(err)
	}
	got := resolveCachedSwiftUIApp(appSupport, resDir)
	if !strings.HasSuffix(got, "Lingo-abcdef12.app") {
		t.Fatalf("expected cached SwiftUI app bundle, got %q", got)
	}
}

func TestParseSwiftVersionAtLeast(t *testing.T) {
	cases := []struct {
		name string
		out  string
		want bool
	}{
		{"apple_5_9", "swift-driver version: 1.87.3 Apple Swift version 5.9.2 (swiftlang-5.9.2.2.56 clang-1500.1.0.2.5)\nTarget: arm64-apple-macosx14.0", true},
		{"apple_5_9_exact", "Apple Swift version 5.9 (swiftlang-5.9.0.128.108)", true},
		{"apple_5_10", "Apple Swift version 5.10 (swiftlang-5.10.0.13)", true},
		{"swift_6_0", "swift-driver version: 1.115 Apple Swift version 6.0 (swiftlang-6.0.0.9.10)\nTarget: arm64-apple-macosx15.0", true},
		{"swift_6_1", "Swift version 6.1.2 (swift-6.1.2-RELEASE)", true},
		{"apple_5_8", "swift-driver version: 1.75.2 Apple Swift version 5.8.1 (swiftlang-5.8.0.124.5)\nTarget: x86_64-apple-macosx13.0", false},
		{"apple_5_7", "Apple Swift version 5.7.2 (swiftlang-5.7.2.135.5)", false},
		{"invalid_empty", "", false},
		{"invalid_garbage", "xcode-select: error: no developer tools were found", false},
	}
	for _, tc := range cases {
		if got := parseSwiftVersionAtLeast(tc.out, 5, 9); got != tc.want {
			t.Errorf("%s: parseSwiftVersionAtLeast(%q, 5, 9) = %v, want %v", tc.name, tc.out, got, tc.want)
		}
	}
}

func TestSwiftBuildPreviouslyFailed(t *testing.T) {
	tmp := t.TempDir()
	resDir := filepath.Join(tmp, "Resources")
	appSupport := filepath.Join(tmp, "Support")
	if err := os.MkdirAll(resDir, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.MkdirAll(filepath.Join(appSupport, "swift-apps"), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(resDir, "swift_source.sha256"), []byte("12345678abcdef\n"), 0o644); err != nil {
		t.Fatal(err)
	}

	ver1 := "swift-driver version: 1.87.3 Apple Swift version 5.9.2"
	if swiftBuildPreviouslyFailed(appSupport, resDir, ver1) {
		t.Fatalf("expected false when failed_build.marker does not exist")
	}

	markerPath := filepath.Join(appSupport, "swift-apps", "failed_build.marker")
	if err := os.WriteFile(markerPath, []byte("12345678|"+ver1+"\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	if !swiftBuildPreviouslyFailed(appSupport, resDir, ver1) {
		t.Fatalf("expected true when hash and Swift version match failed_build.marker")
	}
	if swiftBuildPreviouslyFailed(appSupport, resDir, "Apple Swift version 6.0") {
		t.Fatalf("expected false when Swift toolchain upgraded to newer version")
	}
	if err := os.WriteFile(filepath.Join(resDir, "swift_source.sha256"), []byte("99999999abcdef\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	if swiftBuildPreviouslyFailed(appSupport, resDir, ver1) {
		t.Fatalf("expected false when app swift_source.sha256 changed")
	}
}

func TestWriteSetupStatusAtomic(t *testing.T) {
	tmp := t.TempDir()
	statusPath := filepath.Join(tmp, "setup_status.txt")
	writeSetupStatusAtomic(statusPath, "正在准备 Lingo", "正在安装 PyQt6...")
	raw, err := os.ReadFile(statusPath)
	if err != nil {
		t.Fatalf("read status failed: %v", err)
	}
	if string(raw) != "正在准备 Lingo\n正在安装 PyQt6...\n" {
		t.Fatalf("unexpected status content: %q", string(raw))
	}
	if _, err := os.Stat(statusPath + ".tmp"); !os.IsNotExist(err) {
		t.Fatalf("expected temp file to be renamed away")
	}
}

func TestExtractSetupStatusDetail(t *testing.T) {
	cases := []struct {
		line string
		want string
	}{
		{"[Lingo] 正在为当前环境补装 macOS 原生桌面界面组件...", "正在为当前环境补装 macOS 原生桌面界面组件..."},
		{"Downloading PyQt6-6.7.1-cp312-macosx_12_0_arm64.whl", "正在下载 macOS 原生桌面组件（PyQt6）..."},
		{"Installing collected packages: PyQt6, fastapi", "正在安装核心依赖组件..."},
		{"[12/40] Compiling LingoReelApp MainView.swift", "正在编译原生 SwiftUI 桌面界面..."},
		{"Linking LingoReelApp", "正在链接原生 SwiftUI 可执行文件..."},
		{"   random debug noise   ", ""},
	}
	for _, tc := range cases {
		if got := extractSetupStatusDetail(tc.line); got != tc.want {
			t.Errorf("extractSetupStatusDetail(%q) = %q, want %q", tc.line, got, tc.want)
		}
	}
}

func TestAcquireSetupLockSingleInstance(t *testing.T) {
	tmp := t.TempDir()
	lockPath := filepath.Join(tmp, "setup.lock")

	ok, existing := acquireSetupLock(lockPath)
	if !ok || existing != 0 {
		t.Fatalf("expected initial lock acquire to succeed, got ok=%v existing=%d", ok, existing)
	}

	// Second attempt while current PID holds lock must fail with our PID
	ok2, existing2 := acquireSetupLock(lockPath)
	if ok2 || existing2 != os.Getpid() {
		t.Fatalf("expected busy lock held by pid %d, got ok=%v existing=%d", os.Getpid(), ok2, existing2)
	}

	// Stale dead PID must be reclaimed cleanly
	if err := os.WriteFile(lockPath, []byte("999999\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	ok3, existing3 := acquireSetupLock(lockPath)
	if !ok3 || existing3 != 0 {
		t.Fatalf("expected stale lock reclaim to succeed, got ok=%v existing=%d", ok3, existing3)
	}
}

func TestRunNativeSetupHeadlessEndToEnd(t *testing.T) {
	tmp := t.TempDir()
	appSupport := filepath.Join(tmp, "Support")
	resDir := filepath.Join(tmp, "Resources")
	if err := os.MkdirAll(appSupport, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.MkdirAll(resDir, 0o755); err != nil {
		t.Fatal(err)
	}

	mockBootstrap := filepath.Join(resDir, "bootstrap.sh")
	script := `#!/usr/bin/env bash
set -euo pipefail
echo "[Lingo] 模拟免终端安装开始 ($3)"
echo "NO_TTY=${LINGOREEL_NO_TTY:-0} SKIP_RELAUNCH=${LINGOREEL_SKIP_RELAUNCH:-0}"
echo "Downloading PyQt6-6.7.0.whl"
echo "[Lingo] 模拟安装完成"
exit 0
`
	if err := os.WriteFile(mockBootstrap, []byte(script), 0o755); err != nil {
		t.Fatal(err)
	}

	log := newLogger(filepath.Join(appSupport, "launcher.log"))
	defer log.Close()

	if err := runNativeSetupHeadless(appSupport, resDir, "--native-setup", log); err != nil {
		t.Fatalf("expected headless setup success, got %v", err)
	}

	setupLog, err := os.ReadFile(filepath.Join(appSupport, "setup.log"))
	if err != nil {
		t.Fatalf("expected setup.log to be written: %v", err)
	}
	text := string(setupLog)
	if !strings.Contains(text, "NO_TTY=1 SKIP_RELAUNCH=1") {
		t.Fatalf("expected LINGOREEL_NO_TTY=1 and LINGOREEL_SKIP_RELAUNCH=1 in setup.log, got:\n%s", text)
	}
	if !strings.Contains(text, "模拟免终端安装开始 (--native-setup)") {
		t.Fatalf("expected mode flag passed to bootstrap.sh, got:\n%s", text)
	}
	if _, err := os.Stat(filepath.Join(appSupport, "setup.lock")); !os.IsNotExist(err) {
		t.Fatalf("expected setup.lock cleaned up after completion")
	}
	if _, err := os.Stat(filepath.Join(appSupport, "setup_status.txt")); !os.IsNotExist(err) {
		t.Fatalf("expected setup_status.txt cleaned up after completion")
	}

	// Failure path must return non-nil error and still clean up lock/status
	failScript := "#!/usr/bin/env bash\necho '[Lingo] 模拟失败'\nexit 2\n"
	if err := os.WriteFile(mockBootstrap, []byte(failScript), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := runNativeSetupHeadless(appSupport, resDir, "--native-setup", log); err == nil {
		t.Fatalf("expected non-nil error when bootstrap exits 2")
	}
	if _, err := os.Stat(filepath.Join(appSupport, "setup.lock")); !os.IsNotExist(err) {
		t.Fatalf("expected setup.lock cleaned up after failure")
	}
}


