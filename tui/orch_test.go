package main

import "testing"

func TestOrchNodesFiltersAndSorts(t *testing.T) {
	runs := []Run{
		{RunID: "graph-abc", Status: "running", Events: 2},
		{RunID: "graph-abc:work:1:goal-verify", Status: "blocked", Events: 5},
		{RunID: "graph-abc:work:1:goal", Status: "passed", Events: 471},
		{RunID: "graph-other:work:1:goal", Status: "passed", Events: 9},
		{RunID: "graph-abc:work:1", Status: "running", Events: 7},
	}
	nodes := orchNodes(runs, "graph-abc")
	if len(nodes) != 2 {
		t.Fatalf("want 2 nodes, got %d: %+v", len(nodes), nodes)
	}
	if nodes[0].Name != "goal" || nodes[0].Status != "passed" || nodes[0].Events != 471 {
		t.Fatalf("unexpected first node: %+v", nodes[0])
	}
	if nodes[1].Name != "goal-verify" || nodes[1].Status != "blocked" {
		t.Fatalf("unexpected second node: %+v", nodes[1])
	}
}

func TestGoalFileNamesKeepsPlansAndSorts(t *testing.T) {
	got := goalFileNames([]string{
		"evals/goals/b.md",
		"evals/goals/a.json",
		"evals/goals/notes.txt",
		"evals/goals/upper.MD",
	})
	want := []string{"evals/goals/a.json", "evals/goals/b.md", "evals/goals/upper.MD"}
	if len(got) != len(want) {
		t.Fatalf("want %v, got %v", want, got)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("want %v, got %v", want, got)
		}
	}
}

func TestParseOrchResult(t *testing.T) {
	ok, status := parseOrchResult([]byte(`{"ok": true, "status": "passed", "run_id": "graph-1"}`))
	if !ok || status != "passed" {
		t.Fatalf("unexpected: %v %q", ok, status)
	}
	ok, status = parseOrchResult([]byte("not json"))
	if ok || status != "" {
		t.Fatalf("expected failure on garbage, got %v %q", ok, status)
	}
}
