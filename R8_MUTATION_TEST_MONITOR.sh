#!/bin/bash
# R8 Mutation Test Monitor - Check progress without spamming

PID=1811445
OUTPUT_FILE="/tmp/claude-1000/-home-ubuntu-workspace-hponas/a34327fe-d819-449f-8ecf-1ce4efa4b65a/tasks/bk1266xtg.output"

echo "=== R8 MUTATION TEST MONITOR ==="
echo "Started: 2026-09-22 17:17 UTC"
echo "Expected completion: ~19:45 UTC"
echo ""

if ps -p $PID > /dev/null 2>&1; then
    echo "✓ Process still running (PID $PID)"
    
    # Get last progress line with emoji
    PROGRESS=$(tr '\r' '\n' < "$OUTPUT_FILE" 2>/dev/null | grep -E "🎉|🙁|⏰" | tail -1)
    
    if [ -n "$PROGRESS" ]; then
        echo "Latest progress: $PROGRESS"
    else
        echo "Progress: Generating mutants or running clean tests..."
    fi
    
    # Runtime
    ELAPSED_SEC=$(ps -p $PID -o etimes= 2>/dev/null | tr -d ' ')
    if [ -n "$ELAPSED_SEC" ]; then
        ELAPSED_MIN=$((ELAPSED_SEC / 60))
        echo "Runtime: ${ELAPSED_MIN} minutes"
    fi
    
    echo ""
    echo "Status: IN PROGRESS - check back in 30+ minutes"
else
    echo "✗ Process completed or stopped"
    echo ""
    echo "Checking for results..."
    
    if python -m mutmut results 2>/dev/null | head -5; then
        echo ""
        echo "✓ Results available - ready for analysis"
        echo "Run: python -m mutmut results > /tmp/r8_results.txt"
    else
        echo "✗ No results found - check output file for errors"
    fi
fi
