package main

// Orchestrate: launch `forge run-graph <goal>` from the cockpit and watch the
// run live off the ledger (runs + run detail JSON — the same CLI surface).
// The launch path is exactly what a human types; nothing engine-side changes.

import (
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strings"
	"time"

	tea "github.com/charmbracelet/bubbletea"
)

type orchState struct {
	Goals      []string
	GoalSel    int
	Active     string
	Waiting    bool
	Known      map[string]bool
	Runs       []Run
	Detail     RunDetail
	DoneStatus string
	DoneErr    string
	LogPath    string
}

type orchSnapshotMsg struct {
	known map[string]bool
	err   error
}

type orchTickMsg struct{}

type orchPollMsg struct {
	Runs   []Run
	Active string
	Detail RunDetail
	Err    error
}

type orchDoneMsg struct {
	Err     error
	LogPath string
	OK      bool
	Status  string
}

// OrchNode is one node row of the active run.
type OrchNode struct {
	Name   string
	Status string
	Events int
}

// orchNodes extracts the node rows (goal, goal-verify, ...) for a run.
func orchNodes(runs []Run, active string) []OrchNode {
	prefix := active + ":work:1:"
	var out []OrchNode
	for _, r := range runs {
		if !strings.HasPrefix(r.RunID, prefix) {
			continue
		}
		name := strings.TrimPrefix(r.RunID, prefix)
		if name == "" {
			continue
		}
		out = append(out, OrchNode{Name: name, Status: r.Status, Events: r.Events})
	}
	sort.Slice(out, func(i, j int) bool { return out[i].Name < out[j].Name })
	return out
}

// goalFileNames keeps only launchable plan files, sorted for stable selection.
func goalFileNames(paths []string) []string {
	var names []string
	for _, p := range paths {
		switch strings.ToLower(filepath.Ext(p)) {
		case ".md", ".json":
			names = append(names, p)
		}
	}
	sort.Strings(names)
	return names
}

// parseOrchResult reads the final forge run-graph JSON verdict.
func parseOrchResult(data []byte) (bool, string) {
	var payload struct {
		OK     bool   `json:"ok"`
		Status string `json:"status"`
	}
	if json.Unmarshal(data, &payload) != nil {
		return false, ""
	}
	return payload.OK, payload.Status
}

// LoadGoals lists the plan files a run can be launched from.
func LoadGoals(root string) ([]string, error) {
	var all []string
	for _, pattern := range []string{"evals/goals/*.md", "evals/goals/*.json"} {
		matches, err := filepath.Glob(filepath.Join(root, pattern))
		if err != nil {
			return nil, err
		}
		for _, abs := range matches {
			rel, rerr := filepath.Rel(root, abs)
			if rerr != nil {
				rel = abs
			}
			all = append(all, rel)
		}
	}
	return goalFileNames(all), nil
}

// snapshotRunsCmd records which runs already exist, so the launched run can
// be told apart from history.
func snapshotRunsCmd(root string) tea.Cmd {
	return func() tea.Msg {
		runs, err := LoadRuns(root)
		known := map[string]bool{}
		for _, r := range runs {
			known[r.RunID] = true
		}
		return orchSnapshotMsg{known: known, err: err}
	}
}

// startRunGraphCmd launches the same `forge run-graph` a human would run.
func startRunGraphCmd(root, goal string) tea.Cmd {
	return func() tea.Msg {
		logPath := filepath.Join(root, ".forge", "tui-orchestrate.log")
		cmd := exec.Command("forge", "run-graph", goal)
		cmd.Dir = root
		var data []byte
		f, ferr := os.Create(logPath)
		if ferr == nil {
			cmd.Stdout = f
			cmd.Stderr = f
		}
		runErr := cmd.Run()
		if ferr == nil {
			f.Close()
			if read, rerr := os.ReadFile(logPath); rerr == nil {
				data = read
			}
		}
		ok, status := parseOrchResult(data)
		return orchDoneMsg{Err: runErr, LogPath: logPath, OK: ok, Status: status}
	}
}

func orchTickCmd() tea.Cmd {
	return tea.Tick(2*time.Second, func(time.Time) tea.Msg { return orchTickMsg{} })
}

// pollOrchCmd refreshes the live view from the ledger.
func pollOrchCmd(root, active string, known map[string]bool) tea.Cmd {
	return func() tea.Msg {
		runs, err := LoadRuns(root)
		if err != nil {
			return orchPollMsg{Err: err}
		}
		activeID := active
		if activeID == "" {
			for _, r := range runs {
				if !strings.Contains(r.RunID, ":") && !known[r.RunID] {
					activeID = r.RunID
					break
				}
			}
		}
		msg := orchPollMsg{Runs: runs, Active: activeID}
		if activeID != "" {
			bestID, bestN := "", -1
			for _, r := range runs {
				if strings.HasPrefix(r.RunID, activeID+":") && r.Events > bestN {
					bestID, bestN = r.RunID, r.Events
				}
			}
			if bestID != "" {
				if d, derr := LoadRunDetail(root, bestID); derr == nil {
					msg.Detail = d
				}
			}
		}
		return msg
	}
}

func (m *model) orchTerminal() bool {
	if m.orch.Active == "" {
		return false
	}
	for _, r := range m.orch.Runs {
		if r.RunID == m.orch.Active {
			return r.Status != "running"
		}
	}
	return false
}

func (m *model) renderOrchestrate() string {
	o := &m.orch
	var b strings.Builder

	if o.Active == "" && !o.Waiting {
		b.WriteString(styleSoft.Render("give it something to do — enter launches `forge run-graph <file>` and streams the run here") + "\n\n")
		if len(o.Goals) == 0 {
			b.WriteString(styleSoft.Render("no plan files found under evals/goals/"))
			return b.String()
		}
		for i, g := range o.Goals {
			cursor := "  "
			if i == o.GoalSel {
				cursor = styleTitle.Render("▸ ")
			}
			b.WriteString(cursor + styleFg.Render(g) + "\n")
		}
		b.WriteString("\n" + styleSoft.Render("j/k move · enter launch"))
		return b.String()
	}

	status := "launching…"
	for _, r := range o.Runs {
		if r.RunID == o.Active {
			status = r.Status
		}
	}
	b.WriteString(statusCell(status) + styleFg.Render("  "+o.Active) + "\n")
	if o.Waiting && o.Active == "" {
		b.WriteString(styleSoft.Render(m.spin.View() + " waiting for the run to appear in the ledger") + "\n")
	}

	for _, n := range orchNodes(o.Runs, o.Active) {
		b.WriteString("  " + statusCell(n.Status) + " " + styleFg.Render(padRight(n.Name, 14)) +
			styleSoft.Render(fmt.Sprintf("%d events", n.Events)) + "\n")
	}

	evs := o.Detail.Events
	if len(evs) > 10 {
		evs = evs[len(evs)-10:]
	}
	if len(evs) > 0 {
		b.WriteString("\n" + renderEvents(evs))
	}

	if o.DoneStatus != "" {
		line := styleGood.Render("run finished: " + o.DoneStatus)
		if o.DoneStatus != "passed" {
			line = styleBad.Render("run finished: " + o.DoneStatus)
		}
		b.WriteString("\n" + line)
		if o.DoneErr != "" {
			b.WriteString(styleSoft.Render("  (" + o.DoneErr + ")"))
		}
		b.WriteString("\n" + styleSoft.Render("esc → pick another goal · 2 runs → full ledger detail"))
	}
	return b.String()
}
