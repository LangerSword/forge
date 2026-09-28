package main

import "testing"

func TestParseStatus(t *testing.T) {
	fixture := []byte(`{
	  "forge_version": "0.2.7",
	  "project_root": "/home/lakshaya/forge",
	  "ledger": {"runs": 106, "events": 79485},
	  "ao": {
	    "health": {"status": "ok", "pid": 1045959},
	    "agents": {"supported": [
	      {"id": "opencode", "authStatus": "authorized", "usageCount": 16}
	    ]}
	  }
	}`)
	s, err := parseStatus(fixture)
	if err != nil {
		t.Fatal(err)
	}
	if s.Version != "0.2.7" || s.Runs != 106 || s.Events != 79485 {
		t.Fatalf("unexpected status: %+v", s)
	}
	if s.DaemonState != "ok" || s.DaemonPID != 1045959 {
		t.Fatalf("unexpected daemon: %+v", s)
	}
	if len(s.Agents) != 1 || s.Agents[0].ID != "opencode" || s.Agents[0].Auth != "authorized" || s.Agents[0].Usage != 16 {
		t.Fatalf("unexpected agents: %+v", s.Agents)
	}
}

func TestParseRuns(t *testing.T) {
	fixture := []byte(`{"runs": [
	  {"run_id": "ao-live-smoke-20260928", "goal": "live smoke", "condition": "C0",
	   "harness": "opencode", "status": "passed", "created_at": "2026-09-28T10:13:51+00:00",
	   "event_count": 22}
	]}`)
	runs, err := parseRuns(fixture)
	if err != nil {
		t.Fatal(err)
	}
	if len(runs) != 1 || runs[0].RunID != "ao-live-smoke-20260928" || runs[0].Status != "passed" || runs[0].Events != 22 {
		t.Fatalf("unexpected runs: %+v", runs)
	}
}

func TestParseRunsNullIsEmpty(t *testing.T) {
	runs, err := parseRuns([]byte(`{"runs": null}`))
	if err != nil {
		t.Fatal(err)
	}
	if len(runs) != 0 {
		t.Fatalf("expected empty, got %+v", runs)
	}
}

func TestParseRunDetail(t *testing.T) {
	fixture := []byte(`{
	  "run": {"run_id": "r1", "status": "passed", "goal": "g", "condition": "C0", "harness": "opencode", "created_at": "t", "event_count": 2},
	  "events": [
	    {"id": 1, "ts": "2026-09-28T10:13:51.066658+00:00", "kind": "spawn", "actor": "ao-runner",
	     "payload": {"command": ["./ao", "spawn"]}},
	    {"id": 2, "ts": "2026-09-28T10:13:57.000000+00:00", "kind": "verdict", "actor": "ao-runner", "payload": {}}
	  ]
	}`)
	d, err := parseRunDetail(fixture)
	if err != nil {
		t.Fatal(err)
	}
	if d.Run.RunID != "r1" || len(d.Events) != 2 {
		t.Fatalf("unexpected detail: %+v", d)
	}
	if d.Events[0].Kind != "spawn" || d.Events[0].Actor != "ao-runner" {
		t.Fatalf("unexpected event: %+v", d.Events[0])
	}
	if d.Events[0].Payload == "" || d.Events[0].Payload[0] != '{' {
		t.Fatalf("payload not json: %q", d.Events[0].Payload)
	}
}

func TestParseAOStatusRunningAndStopped(t *testing.T) {
	running := []byte(`{"ok": true, "daemon": {"state": "ready", "pid": 1045959, "port": 3001, "uptime": "25m"}}`)
	ao, err := parseAOStatus(running)
	if err != nil {
		t.Fatal(err)
	}
	if ao.State != "ready" || ao.PID != 1045959 || ao.Port != 3001 || ao.Uptime != "25m" {
		t.Fatalf("unexpected ao: %+v", ao)
	}
	stopped := []byte(`{"ok": true, "daemon": {"state": "stopped"}}`)
	ao, err = parseAOStatus(stopped)
	if err != nil {
		t.Fatal(err)
	}
	if ao.State != "stopped" {
		t.Fatalf("unexpected ao: %+v", ao)
	}
}

func TestParseHarnesses(t *testing.T) {
	fixture := []byte(`{"harnesses": [
	  {"name": "opencode", "state": "not_smoke_tested", "ready": false},
	  {"name": "codex", "state": "ready", "ready": true}
	]}`)
	harnesses, err := parseHarnesses(fixture)
	if err != nil {
		t.Fatal(err)
	}
	if len(harnesses) != 2 || harnesses[1].Name != "codex" || !harnesses[1].Ready {
		t.Fatalf("unexpected harnesses: %+v", harnesses)
	}
}

func TestParseReview(t *testing.T) {
	fixture := []byte(`{
	  "ok": true, "all_suites_100": true,
	  "suites": {
	    "gate": {"suite": "gate", "total_cases": 1800, "summary": {"all_dimensions_100": true}},
	    "policy": {"suite": "policy", "total_cases": 11, "summary": {"all_dimensions_100": true}}
	  }
	}`)
	r, err := parseReview(fixture)
	if err != nil {
		t.Fatal(err)
	}
	if !r.AllOK || len(r.Suites) != 2 {
		t.Fatalf("unexpected review: %+v", r)
	}
	if r.Suites[0].Name != "gate" || r.Suites[0].Total != 1800 || !r.Suites[0].All100 {
		t.Fatalf("unexpected suite: %+v", r.Suites[0])
	}
}

func TestParseReviewRejectsErrorPayload(t *testing.T) {
	_, err := parseReview([]byte(`{"ok": false, "error": "ao_unavailable"}`))
	if err == nil {
		t.Fatal("expected error for payload without suites")
	}
}

func TestAdjustOffsetKeepsSelectionVisible(t *testing.T) {
	if got := adjustOffset(5, 0, 10); got != 0 {
		t.Fatalf("no scroll expected, got %d", got)
	}
	if got := adjustOffset(12, 0, 10); got != 3 {
		t.Fatalf("expected scroll to 3, got %d", got)
	}
	if got := adjustOffset(2, 5, 10); got != 2 {
		t.Fatalf("expected scroll up to 2, got %d", got)
	}
}