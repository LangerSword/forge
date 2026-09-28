package main

// forge-tui — the Forge cockpit.
//
// Reads the same JSON surface the forge CLI exposes (status, runs, run,
// ao status, harnesses, review) and renders it in a bubbletea TUI.

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"

	"github.com/charmbracelet/bubbles/spinner"
	"github.com/charmbracelet/bubbles/viewport"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
)

type page int

const (
	pageStatus page = iota
	pageRuns
	pageOrchestrate
	pageAO
	pageReview
	pageHelp
)

var pageNames = []string{"status", "runs", "orchestrate", "ao", "review", "help"}

const (
	colFg     = lipgloss.Color("#D7D7DE")
	colSoft   = lipgloss.Color("#6E6E7C")
	colAccent = lipgloss.Color("#8B7CFF")
	colGood   = lipgloss.Color("#4CD97B")
	colBad    = lipgloss.Color("#FF5C7A")
	colWarn   = lipgloss.Color("#FFC24B")
	colPanel  = lipgloss.Color("#2A2A34")
)

var (
	styleTitle  = lipgloss.NewStyle().Bold(true).Foreground(colAccent)
	styleSoft   = lipgloss.NewStyle().Foreground(colSoft)
	styleFg     = lipgloss.NewStyle().Foreground(colFg)
	styleGood   = lipgloss.NewStyle().Foreground(colGood)
	styleBad    = lipgloss.NewStyle().Foreground(colBad)
	styleWarn   = lipgloss.NewStyle().Foreground(colWarn)
	styleTabOn  = lipgloss.NewStyle().Background(colAccent).Foreground(lipgloss.Color("#0E0E12")).Bold(true).Padding(0, 1)
	styleTabOff = lipgloss.NewStyle().Foreground(colSoft).Padding(0, 1)
	stylePanel  = lipgloss.NewStyle().Border(lipgloss.RoundedBorder()).BorderForeground(colPanel).Padding(0, 2)
)

type loadedMsg struct {
	tab  page
	data any
	note string
	err  error
}

type detailMsg struct {
	detail RunDetail
	err    error
}

type model struct {
	root string
	tab  page
	w, h int
	spin spinner.Model
	load bool

	status StatusData
	runs   []Run
	runSel int
	runOff int

	detail *RunDetail
	events viewport.Model

	ao     AOData
	aoNote string

	review ReviewData
	orch   orchState
	err    error
}

func newModel(root string) *model {
	sp := spinner.New()
	sp.Spinner = spinner.Dot
	sp.Style = lipgloss.NewStyle().Foreground(colAccent)
	return &model{
		root:   root,
		tab:    pageStatus,
		w:      100,
		h:      30,
		load:   true,
		spin:   sp,
		events: viewport.New(40, 10),
	}
}

func loadTabCmd(root string, tab page) tea.Cmd {
	return func() tea.Msg {
		switch tab {
		case pageStatus:
			d, err := LoadStatus(root)
			return loadedMsg{tab: tab, data: d, err: err}
		case pageRuns:
			d, err := LoadRuns(root)
			return loadedMsg{tab: tab, data: d, err: err}
		case pageAO:
			d, note, err := LoadAO(root)
			return loadedMsg{tab: tab, data: d, note: note, err: err}
		case pageReview:
			d, err := LoadReview(root)
			return loadedMsg{tab: tab, data: d, err: err}
		case pageOrchestrate:
			d, err := LoadGoals(root)
			return loadedMsg{tab: tab, data: d, err: err}
		}
		return loadedMsg{tab: tab}
	}
}

func openRunCmd(root, id string) tea.Cmd {
	return func() tea.Msg {
		d, err := LoadRunDetail(root, id)
		return detailMsg{detail: d, err: err}
	}
}

func (m *model) Init() tea.Cmd {
	return tea.Batch(m.spin.Tick, loadTabCmd(m.root, m.tab))
}

func (m *model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.w, m.h = msg.Width, msg.Height
		m.resizeDetailViewport()
		return m, nil
	case spinner.TickMsg:
		var cmd tea.Cmd
		m.spin, cmd = m.spin.Update(msg)
		if m.load {
			return m, cmd
		}
		return m, nil
	case loadedMsg:
		m.load = false
		m.err = msg.err
		if msg.err == nil {
			switch msg.tab {
			case pageStatus:
				if d, ok := msg.data.(StatusData); ok {
					m.status = d
				}
			case pageRuns:
				if runs, ok := msg.data.([]Run); ok {
					m.runs = runs
					if m.runSel >= len(m.runs) {
						m.runSel = max(0, len(m.runs)-1)
					}
					m.runOff = adjustOffset(m.runSel, m.runOff, m.runsVisible())
				}
			case pageAO:
				if d, ok := msg.data.(AOData); ok {
					m.ao = d
					m.aoNote = msg.note
				}
			case pageReview:
				if d, ok := msg.data.(ReviewData); ok {
					m.review = d
				}
			case pageOrchestrate:
				if goals, ok := msg.data.([]string); ok {
					m.orch.Goals = goals
					if m.orch.GoalSel >= len(goals) {
						m.orch.GoalSel = max(0, len(goals)-1)
					}
				}
			}
		}
		return m, nil
	case detailMsg:
		m.load = false
		if msg.err != nil {
			m.err = msg.err
			return m, nil
		}
		d := msg.detail
		m.detail = &d
		m.err = nil
		m.events.SetContent(renderEvents(m.detail.Events))
		m.events.SetYOffset(0)
		m.resizeDetailViewport()
		return m, nil
	case orchSnapshotMsg:
		m.orch.Waiting = true
		m.orch.Known = msg.known
		if msg.err != nil {
			m.err = msg.err
			return m, nil
		}
		if len(m.orch.Goals) == 0 {
			return m, nil
		}
		return m, tea.Batch(startRunGraphCmd(m.root, m.orch.Goals[m.orch.GoalSel]), orchTickCmd())
	case orchTickMsg:
		if m.orch.Active == "" && !m.orch.Waiting {
			return m, nil
		}
		if m.orch.Active != "" && m.orchTerminal() {
			return m, nil
		}
		return m, pollOrchCmd(m.root, m.orch.Active, m.orch.Known)
	case orchPollMsg:
		m.orch.Runs = msg.Runs
		if msg.Active != "" {
			m.orch.Active = msg.Active
		}
		if msg.Detail.Run.RunID != "" {
			m.orch.Detail = msg.Detail
		}
		if msg.Err != nil {
			m.err = msg.Err
		}
		if m.orch.Active != "" && !m.orchTerminal() {
			return m, orchTickCmd()
		}
		return m, nil
	case orchDoneMsg:
		m.orch.Waiting = false
		m.orch.DoneErr = ""
		if msg.Status != "" {
			m.orch.DoneStatus = msg.Status
		} else if msg.OK {
			m.orch.DoneStatus = "passed"
		} else if m.orch.DoneStatus == "" {
			m.orch.DoneStatus = "failed"
		}
		if msg.Err != nil {
			m.orch.DoneErr = msg.Err.Error()
		}
		m.orch.LogPath = msg.LogPath
		return m, nil
	case tea.KeyMsg:
		return m.handleKey(msg)
	}
	return m, nil
}

func (m *model) handleKey(msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	key := msg.String()
	switch key {
	case "ctrl+c":
		return m, tea.Quit
	case "q":
		if m.detail != nil {
			m.detail = nil
			return m, nil
		}
		return m, tea.Quit
	case "esc":
		if m.detail != nil {
			m.detail = nil
			return m, nil
		}
		if m.tab == pageOrchestrate && m.orch.DoneStatus != "" {
			m.orch = orchState{Goals: m.orch.Goals}
		}
		return m, nil
	case "1", "2", "3", "4", "5", "6":
		idx := page(int(key[0] - '1'))
		if m.tab != idx {
			m.tab = idx
			m.detail = nil
			m.err = nil
			m.load = true
			return m, tea.Batch(m.spin.Tick, loadTabCmd(m.root, m.tab))
		}
		return m, nil
	case "r":
		m.err = nil
		m.load = true
		if m.detail != nil && m.tab == pageRuns {
			return m, tea.Batch(m.spin.Tick, openRunCmd(m.root, m.detail.Run.RunID))
		}
		return m, tea.Batch(m.spin.Tick, loadTabCmd(m.root, m.tab))
	case "up", "k":
		if m.detail == nil {
			if m.tab == pageRuns && m.runSel > 0 {
				m.runSel--
				m.runOff = adjustOffset(m.runSel, m.runOff, m.runsVisible())
			}
			if m.tab == pageOrchestrate && m.orch.Active == "" && !m.orch.Waiting && m.orch.GoalSel > 0 {
				m.orch.GoalSel--
			}
			return m, nil
		}
	case "down", "j":
		if m.detail == nil {
			if m.tab == pageRuns && m.runSel < len(m.runs)-1 {
				m.runSel++
				m.runOff = adjustOffset(m.runSel, m.runOff, m.runsVisible())
			}
			if m.tab == pageOrchestrate && m.orch.Active == "" && !m.orch.Waiting && m.orch.GoalSel < len(m.orch.Goals)-1 {
				m.orch.GoalSel++
			}
			return m, nil
		}
	case "enter":
		if m.tab == pageRuns && m.detail == nil && len(m.runs) > 0 {
			m.load = true
			return m, tea.Batch(m.spin.Tick, openRunCmd(m.root, m.runs[m.runSel].RunID))
		}
		if m.tab == pageOrchestrate && m.detail == nil && m.orch.Active == "" && !m.orch.Waiting && len(m.orch.Goals) > 0 {
			return m, snapshotRunsCmd(m.root)
		}
		return m, nil
	}
	if m.detail != nil {
		switch key {
		case "j":
			m.events.SetYOffset(m.events.YOffset + 1)
			return m, nil
		case "k":
			off := m.events.YOffset - 1
			if off < 0 {
				off = 0
			}
			m.events.SetYOffset(off)
			return m, nil
		}
		var cmd tea.Cmd
		m.events, cmd = m.events.Update(msg)
		return m, cmd
	}
	return m, nil
}

func (m *model) View() string {
	return lipgloss.JoinVertical(
		lipgloss.Left,
		m.renderHeader(),
		m.renderTabs(),
		m.renderBody(),
		styleSoft.Render("  1 status · 2 runs · 3 orchestrate · 4 ao · 5 review · 6 help    r refresh    enter open/launch    esc back    q quit"),
	)
}

func (m *model) renderHeader() string {
	left := lipgloss.JoinHorizontal(lipgloss.Top,
		styleTitle.Render("FORGE"),
		styleSoft.Render("  ·  fleet commander"),
	)
	badge := styleSoft.Render("◌ daemon unknown")
	switch m.status.DaemonState {
	case "ok", "ready":
		badge = styleGood.Render("● daemon ready")
	case "stopped", "stale":
		badge = styleBad.Render("○ daemon " + m.status.DaemonState)
	}
	right := styleSoft.Render("v"+m.status.Version+"   ") + badge
	gap := m.w - lipgloss.Width(left) - lipgloss.Width(right)
	if gap < 1 {
		gap = 1
	}
	return left + strings.Repeat(" ", gap) + right + "\n"
}

func (m *model) renderTabs() string {
	parts := make([]string, 0, len(pageNames))
	for i, name := range pageNames {
		label := fmt.Sprintf("%d %s", i+1, name)
		if page(i) == m.tab {
			parts = append(parts, styleTabOn.Render(label))
		} else {
			parts = append(parts, styleTabOff.Render(label))
		}
	}
	return strings.Join(parts, " ") + "\n"
}

func (m *model) renderBody() string {
	panelW := m.w - 2
	panelH := m.bodyHeight() - 2
	title := ""
	var content string
	switch {
	case m.detail != nil:
		title = "run " + m.detail.Run.RunID
		content = m.renderDetail()
	case m.tab == pageStatus:
		title = "status"
		content = m.renderStatus()
	case m.tab == pageRuns:
		title = fmt.Sprintf("runs · %d", len(m.runs))
		content = m.renderRuns()
	case m.tab == pageOrchestrate:
		title = "orchestrate — give it something to do"
		content = m.renderOrchestrate()
	case m.tab == pageAO:
		title = "agent orchestrator"
		content = m.renderAO()
	case m.tab == pageReview:
		title = "verdict systems — self-grading"
		content = m.renderReview()
	case m.tab == pageHelp:
		title = "help"
		content = renderHelp()
	}
	if m.load {
		content = m.spin.View() + styleSoft.Render(" loading…")
	} else if m.err != nil {
		content = styleBad.Render("✗ " + m.err.Error())
	}
	inner := styleTitle.Render(strings.ToUpper(title)) + "\n\n" + content
	return stylePanel.Width(panelW).Height(panelH).Render(inner)
}

func (m *model) renderStatus() string {
	s := m.status
	var b strings.Builder
	rows := [][2]string{
		{"version", s.Version},
		{"root", s.Root},
		{"ledger", fmt.Sprintf("%d runs · %d events", s.Runs, s.Events)},
		{"daemon", m.daemonLine()},
	}
	for _, r := range rows {
		b.WriteString(styleSoft.Render(padRight(r[0], 10)) + styleFg.Render(r[1]) + "\n")
	}
	b.WriteString("\n" + styleSoft.Render("agents") + "\n")
	for _, a := range s.Agents {
		mark := styleBad.Render("✗")
		if a.Auth == "authorized" {
			mark = styleGood.Render("✓")
		}
		b.WriteString("  " + mark + " " + styleFg.Render(padRight(a.ID, 14)) +
			styleSoft.Render(a.Auth) + styleSoft.Render(fmt.Sprintf("  · %d sessions", a.Usage)) + "\n")
	}
	return b.String()
}

func (m *model) daemonLine() string {
	switch m.status.DaemonState {
	case "ok", "ready":
		return fmt.Sprintf("ready · pid %d", m.status.DaemonPID)
	case "":
		return "unknown"
	default:
		return m.status.DaemonState
	}
}

func (m *model) renderRuns() string {
	if len(m.runs) == 0 {
		return styleSoft.Render("no runs in the ledger yet")
	}
	visible := m.runsVisible()
	end := m.runOff + visible
	if end > len(m.runs) {
		end = len(m.runs)
	}
	var b strings.Builder
	for i := m.runOff; i < end; i++ {
		r := m.runs[i]
		cursor := "  "
		if i == m.runSel {
			cursor = styleTitle.Render("▸ ")
		}
		when := r.CreatedAt
		if len(when) >= 16 {
			when = when[:16]
		}
		goalW := m.w - 2 - 2 - 10 - 28 - 18 - 4
		if goalW < 10 {
			goalW = 10
		}
		b.WriteString(cursor + statusCell(r.Status) + " " +
			styleFg.Render(padRight(r.RunID, 28)) +
			styleSoft.Render(padRight(when, 18)+truncate(r.Goal, goalW)) + "\n")
	}
	if len(m.runs) > visible {
		b.WriteString(styleSoft.Render(fmt.Sprintf("\n  %d–%d of %d", m.runOff+1, end, len(m.runs))))
	}
	return b.String()
}

func (m *model) renderDetail() string {
	d := m.detail
	head := statusCell(d.Run.Status) + styleFg.Render("  "+d.Run.Condition+" · "+d.Run.Harness) +
		styleSoft.Render("  "+d.Run.CreatedAt)
	goal := styleSoft.Render(truncate(d.Run.Goal, m.w-10))
	return head + "\n" + goal + "\n\n" + m.events.View()
}

func (m *model) renderAO() string {
	a := m.ao
	var b strings.Builder
	state := styleWarn.Render(a.State)
	switch a.State {
	case "ready":
		state = styleGood.Render(a.State)
	case "stopped", "stale":
		state = styleBad.Render(a.State)
	}
	b.WriteString(styleSoft.Render(padRight("daemon", 10)) + state)
	if a.PID > 0 {
		b.WriteString(styleSoft.Render(fmt.Sprintf("  pid %d", a.PID)))
	}
	if a.Port > 0 {
		b.WriteString(styleSoft.Render(fmt.Sprintf("  :%d", a.Port)))
	}
	if a.Uptime != "" {
		b.WriteString(styleSoft.Render("  up " + a.Uptime))
	}
	b.WriteString("\n\n" + styleSoft.Render("harnesses") + "\n")
	for _, h := range a.Harnesses {
		mark := styleSoft.Render("○")
		st := styleSoft
		if h.Ready {
			mark = styleGood.Render("●")
			st = styleGood
		}
		b.WriteString("  " + mark + " " + styleFg.Render(padRight(h.Name, 14)) + st.Render(h.State) + "\n")
	}
	if m.aoNote != "" {
		b.WriteString("\n" + styleWarn.Render("⚠ "+m.aoNote) + "\n")
	}
	b.WriteString("\n" + styleSoft.Render("forge ao start · stop · status for the full lifecycle"))
	return b.String()
}

func (m *model) renderReview() string {
	if len(m.review.Suites) == 0 {
		return styleSoft.Render("no review loaded — press r")
	}
	var b strings.Builder
	if m.review.AllOK {
		b.WriteString(styleGood.Bold(true).Render("ALL SUITES 100%") + "\n\n")
	} else {
		b.WriteString(styleBad.Bold(true).Render("REGRESSIONS PRESENT") + "\n\n")
	}
	for _, s := range m.review.Suites {
		mark := styleBad.Render("✗")
		if s.All100 {
			mark = styleGood.Render("✓")
		}
		b.WriteString("  " + mark + " " + styleFg.Render(padRight(s.Name, 12)) +
			styleSoft.Render(fmt.Sprintf("%d cases", s.Total)) + "\n")
	}
	b.WriteString("\n" + styleSoft.Render("deterministic oracles · press r to re-grade"))
	return b.String()
}

func renderHelp() string {
	lines := []string{
		styleFg.Render("forge-tui") + styleSoft.Render(" — cockpit over the forge CLI JSON surface"),
		"",
		styleSoft.Render("keys"),
		styleFg.Render("  1-6") + styleSoft.Render("      switch pages"),
		styleFg.Render("  j / k") + styleSoft.Render("    move (or scroll events)"),
		styleFg.Render("  enter") + styleSoft.Render("    open run detail · launch a goal (page 3)"),
		styleFg.Render("  esc") + styleSoft.Render("      back"),
		styleFg.Render("  r") + styleSoft.Render("        refresh"),
		styleFg.Render("  q") + styleSoft.Render("        quit"),
		"",
		styleSoft.Render("root: FORGE_ROOT env or --root= (default ~/forge) · forge must be on PATH"),
	}
	return strings.Join(lines, "\n")
}

func renderEvents(events []Event) string {
	var b strings.Builder
	for _, e := range events {
		when := e.TS
		if len(when) >= 19 {
			when = when[11:19]
		}
		b.WriteString(styleSoft.Render(when) + " " + styleTitle.Render(padRight(e.Kind, 12)) +
			styleSoft.Render(padRight(e.Actor, 14)) + styleFg.Render(e.Payload) + "\n")
	}
	return b.String()
}

// ---- layout helpers ----

func (m *model) bodyHeight() int {
	h := m.h - 6
	if h < 6 {
		h = 6
	}
	return h
}

func (m *model) runsVisible() int {
	v := m.bodyHeight() - 5
	if v < 1 {
		v = 1
	}
	return v
}

func (m *model) resizeDetailViewport() {
	if m.detail == nil {
		return
	}
	innerW := m.w - 10
	if innerW < 20 {
		innerW = 20
	}
	innerH := m.bodyHeight() - 10
	if innerH < 3 {
		innerH = 3
	}
	m.events.Width = innerW
	m.events.Height = innerH
}

func adjustOffset(sel, off, visible int) int {
	if sel < off {
		return sel
	}
	if sel >= off+visible {
		return sel - visible + 1
	}
	return off
}

func padRight(s string, n int) string {
	if len(s) >= n {
		return s
	}
	return s + strings.Repeat(" ", n-len(s))
}

func truncate(s string, n int) string {
	s = strings.ReplaceAll(s, "\n", " ")
	if len(s) > n {
		return s[:n] + "…"
	}
	return s
}

func statusCell(status string) string {
	cell := padRight(status, 9)
	switch status {
	case "passed":
		return styleGood.Render(cell)
	case "failed":
		return styleBad.Render(cell)
	case "blocked", "stopped":
		return styleWarn.Render(cell)
	case "running":
		return styleTitle.Render(cell)
	default:
		return styleSoft.Render(cell)
	}
}

// ---- non-interactive dump (CI / verification) ----

func runDump(root string) int {
	fmt.Println("FORGE — dump · root:", root)
	st, err := LoadStatus(root)
	if err != nil {
		fmt.Println("status error:", err)
		return 1
	}
	fmt.Printf("version %s · ledger %d runs / %d events · daemon %s (pid %d)\n",
		st.Version, st.Runs, st.Events, st.DaemonState, st.DaemonPID)
	for _, a := range st.Agents {
		fmt.Printf("agent: %s (%s, %d sessions)\n", a.ID, a.Auth, a.Usage)
	}
	runs, err := LoadRuns(root)
	if err != nil {
		fmt.Println("runs error:", err)
	} else {
		fmt.Printf("runs: %d\n", len(runs))
		limit := len(runs)
		if limit > 5 {
			limit = 5
		}
		for _, r := range runs[:limit] {
			fmt.Printf("  %-9s %-26s %s\n", r.Status, r.RunID, truncate(r.Goal, 60))
		}
	}
	ao, note, err := LoadAO(root)
	if err != nil {
		fmt.Println("ao error:", err)
	} else {
		fmt.Printf("ao: %s pid=%d port=%d uptime=%s harnesses=%d\n", ao.State, ao.PID, ao.Port, ao.Uptime, len(ao.Harnesses))
		if note != "" {
			fmt.Println("ao note:", note)
		}
	}
	rev, err := LoadReview(root)
	if err != nil {
		fmt.Println("review error:", err)
	} else {
		fmt.Printf("review: all_suites_100=%v\n", rev.AllOK)
		for _, s := range rev.Suites {
			fmt.Printf("  %-8s %5d cases  all100=%v\n", s.Name, s.Total, s.All100)
		}
	}
	return 0
}

func main() {
	root := os.Getenv("FORGE_ROOT")
	if root == "" {
		home, err := os.UserHomeDir()
		if err == nil {
			root = filepath.Join(home, "forge")
		}
	}
	dump := false
	for _, a := range os.Args[1:] {
		switch {
		case a == "--dump":
			dump = true
		case strings.HasPrefix(a, "--root="):
			root = strings.TrimPrefix(a, "--root=")
		}
	}
	if _, err := exec.LookPath("forge"); err != nil {
		fmt.Fprintln(os.Stderr, "forge-tui: `forge` not found on PATH — install it first (uv tool install --editable <repo>)")
		os.Exit(1)
	}
	if dump {
		os.Exit(runDump(root))
	}
	p := tea.NewProgram(newModel(root), tea.WithAltScreen())
	if _, err := p.Run(); err != nil {
		fmt.Fprintln(os.Stderr, "forge-tui:", err)
		os.Exit(1)
	}
}