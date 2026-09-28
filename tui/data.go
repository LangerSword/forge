package main

// Data layer: every value comes from the `forge` CLI JSON surface — the same
// API humans use. No second state model, no direct ledger reads.
//
// Failure discipline: a forge command that fails is surfaced with its own
// JSON error message (forge prints {"ok": false, "message": ...}), never
// swallowed and never faked.

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os/exec"
	"sort"
	"strings"
)

type forgeError struct {
	Command string
	Message string
}

func (e *forgeError) Error() string { return e.Command + ": " + e.Message }

func firstLine(s string) string {
	if i := strings.IndexByte(s, '\n'); i >= 0 {
		return s[:i]
	}
	return s
}

func forgeErrorMessage(stdout []byte) string {
	var payload struct {
		Message string `json:"message"`
		Error   string `json:"error"`
	}
	if json.Unmarshal(stdout, &payload) == nil {
		if payload.Message != "" {
			return payload.Message
		}
		if payload.Error != "" {
			return payload.Error
		}
	}
	return ""
}

func runForge(root string, args ...string) ([]byte, error) {
	cmd := exec.Command("forge", args...)
	cmd.Dir = root
	var out, errb bytes.Buffer
	cmd.Stdout = &out
	cmd.Stderr = &errb
	if err := cmd.Run(); err != nil {
		detail := forgeErrorMessage(out.Bytes())
		if detail == "" {
			detail = strings.TrimSpace(errb.String())
		}
		if detail == "" {
			detail = err.Error()
		}
		return out.Bytes(), &forgeError{Command: "forge " + strings.Join(args, " "), Message: firstLine(detail)}
	}
	return out.Bytes(), nil
}

// ---- typed views of forge output ----

type Agent struct {
	ID    string
	Auth  string
	Usage int
}

type StatusData struct {
	Version     string
	Root        string
	Runs        int
	Events      int
	DaemonState string
	DaemonPID   int
	Agents      []Agent
}

type Run struct {
	RunID     string `json:"run_id"`
	Goal      string `json:"goal"`
	Condition string `json:"condition"`
	Harness   string `json:"harness"`
	Status    string `json:"status"`
	CreatedAt string `json:"created_at"`
	Events    int    `json:"event_count"`
}

type Event struct {
	TS      string
	Kind    string
	Actor   string
	Payload string
}

type RunDetail struct {
	Run    Run
	Events []Event
}

type Harness struct {
	Name  string
	State string
	Ready bool
}

type AOData struct {
	State     string
	PID       int
	Port      int
	Uptime    string
	Harnesses []Harness
}

type Suite struct {
	Name   string
	Total  int
	All100 bool
}

type ReviewData struct {
	AllOK  bool
	Suites []Suite
}

// ---- pure parsers (tested without subprocesses) ----

func parseStatus(data []byte) (StatusData, error) {
	var payload struct {
		Version string `json:"forge_version"`
		Root    string `json:"project_root"`
		Ledger  struct {
			Runs   int `json:"runs"`
			Events int `json:"events"`
		} `json:"ledger"`
		AO struct {
			Health struct {
				Status string `json:"status"`
				PID    int    `json:"pid"`
			} `json:"health"`
			Agents struct {
				Supported []struct {
					ID    string `json:"id"`
					Auth  string `json:"authStatus"`
					Usage int    `json:"usageCount"`
				} `json:"supported"`
			} `json:"agents"`
		} `json:"ao"`
	}
	if err := json.Unmarshal(data, &payload); err != nil {
		return StatusData{}, err
	}
	s := StatusData{
		Version:     payload.Version,
		Root:        payload.Root,
		Runs:        payload.Ledger.Runs,
		Events:      payload.Ledger.Events,
		DaemonState: payload.AO.Health.Status,
		DaemonPID:   payload.AO.Health.PID,
	}
	for _, a := range payload.AO.Agents.Supported {
		s.Agents = append(s.Agents, Agent{ID: a.ID, Auth: a.Auth, Usage: a.Usage})
	}
	return s, nil
}

func parseRuns(data []byte) ([]Run, error) {
	var payload struct {
		Runs []Run `json:"runs"`
	}
	if err := json.Unmarshal(data, &payload); err != nil {
		return nil, err
	}
	if payload.Runs == nil {
		return []Run{}, nil
	}
	return payload.Runs, nil
}

func parseRunDetail(data []byte) (RunDetail, error) {
	var payload struct {
		Run    Run `json:"run"`
		Events []struct {
			TS      string          `json:"ts"`
			Kind    string          `json:"kind"`
			Actor   string          `json:"actor"`
			Payload json.RawMessage `json:"payload"`
		} `json:"events"`
	}
	if err := json.Unmarshal(data, &payload); err != nil {
		return RunDetail{}, err
	}
	detail := RunDetail{Run: payload.Run}
	for _, e := range payload.Events {
		p := strings.TrimSpace(string(e.Payload))
		if len(p) > 220 {
			p = p[:220] + "…"
		}
		detail.Events = append(detail.Events, Event{TS: e.TS, Kind: e.Kind, Actor: e.Actor, Payload: p})
	}
	return detail, nil
}

func parseAOStatus(data []byte) (AOData, error) {
	var payload struct {
		Daemon struct {
			State  string `json:"state"`
			PID    int    `json:"pid"`
			Port   int    `json:"port"`
			Uptime string `json:"uptime"`
		} `json:"daemon"`
	}
	if err := json.Unmarshal(data, &payload); err != nil {
		return AOData{}, err
	}
	return AOData{
		State:  payload.Daemon.State,
		PID:    payload.Daemon.PID,
		Port:   payload.Daemon.Port,
		Uptime: payload.Daemon.Uptime,
	}, nil
}

func parseHarnesses(data []byte) ([]Harness, error) {
	var payload struct {
		Harnesses []struct {
			Name  string `json:"name"`
			State string `json:"state"`
			Ready bool   `json:"ready"`
		} `json:"harnesses"`
	}
	if err := json.Unmarshal(data, &payload); err != nil {
		return nil, err
	}
	if payload.Harnesses == nil {
		return nil, fmt.Errorf("no harnesses in output")
	}
	out := make([]Harness, 0, len(payload.Harnesses))
	for _, h := range payload.Harnesses {
		out = append(out, Harness{Name: h.Name, State: h.State, Ready: h.Ready})
	}
	return out, nil
}

func parseReview(data []byte) (ReviewData, error) {
	var payload struct {
		All100 bool `json:"all_suites_100"`
		Suites map[string]struct {
			Total   int `json:"total_cases"`
			Summary struct {
				All100 bool `json:"all_dimensions_100"`
			} `json:"summary"`
		} `json:"suites"`
	}
	if err := json.Unmarshal(data, &payload); err != nil {
		return ReviewData{}, err
	}
	if payload.Suites == nil {
		return ReviewData{}, fmt.Errorf("no suites in review output")
	}
	names := make([]string, 0, len(payload.Suites))
	for name := range payload.Suites {
		names = append(names, name)
	}
	sort.Strings(names)
	review := ReviewData{AllOK: payload.All100}
	for _, name := range names {
		s := payload.Suites[name]
		review.Suites = append(review.Suites, Suite{Name: name, Total: s.Total, All100: s.Summary.All100})
	}
	return review, nil
}

// ---- loaders (subprocess + parser) ----

func LoadStatus(root string) (StatusData, error) {
	out, err := runForge(root, "status")
	if err != nil {
		return StatusData{}, err
	}
	return parseStatus(out)
}

func LoadRuns(root string) ([]Run, error) {
	out, err := runForge(root, "runs")
	if err != nil {
		return nil, err
	}
	return parseRuns(out)
}

func LoadRunDetail(root, id string) (RunDetail, error) {
	out, err := runForge(root, "run", id)
	if err != nil {
		return RunDetail{}, err
	}
	return parseRunDetail(out)
}

func LoadAO(root string) (AOData, string, error) {
	out, err := runForge(root, "ao", "status")
	if err != nil {
		return AOData{}, "", err
	}
	data, err := parseAOStatus(out)
	if err != nil {
		return AOData{}, "", err
	}
	hout, herr := runForge(root, "harnesses")
	if herr != nil {
		return data, herr.Error(), nil
	}
	harnesses, perr := parseHarnesses(hout)
	if perr != nil {
		return data, perr.Error(), nil
	}
	data.Harnesses = harnesses
	return data, "", nil
}

func LoadReview(root string) (ReviewData, error) {
	out, cmdErr := runForge(root, "review")
	data, parseErr := parseReview(out)
	if parseErr != nil {
		if cmdErr != nil {
			return ReviewData{}, cmdErr
		}
		return ReviewData{}, parseErr
	}
	return data, nil
}