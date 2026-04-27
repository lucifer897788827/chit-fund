from scripts.performance_report import format_report, summarize_timings


def test_summarize_timings_calculates_average_ms():
    report = summarize_timings(
        {
            "dashboard": [100.0, 140.0],
            "admin users": [240.0],
        }
    )

    assert report == [
        {"endpoint": "dashboard", "averageMs": 120.0},
        {"endpoint": "admin users", "averageMs": 240.0},
    ]


def test_format_report_outputs_endpoint_average_lines():
    text = format_report(
        [
            {"endpoint": "dashboard", "averageMs": 120.0},
            {"endpoint": "admin users", "averageMs": 240.0},
        ]
    )

    assert "Endpoint -> Avg Time" in text
    assert "dashboard -> 120.00ms" in text
    assert "admin users -> 240.00ms" in text
