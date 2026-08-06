from collections import defaultdict

from .models.constants import WEEKDAYS


def _wrap_text(text, max_chars):
    words = text.split()
    lines = []
    current = ""
    for word in words:
        if not current:
            current = word
        elif len(current) + 1 + len(word) <= max_chars:
            current += " " + word
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [""]


def build_svg_data(groups_with_time):
    if not groups_with_time:
        return None

    time_axis_w = 52
    header_h = 40
    time_padding = 10
    col_w = 160
    hour_px = 60
    padding = 3
    font_size = 12
    line_height = 15

    all_start = [g.start_time.hour * 60 + g.start_time.minute for g in groups_with_time]
    all_end = [g.end_time.hour * 60 + g.end_time.minute for g in groups_with_time]
    min_time = min(9 * 60, (min(all_start) // 60) * 60)
    max_time = max(21 * 60, ((max(all_end) + 59) // 60) * 60)

    by_weekday = defaultdict(list)
    for group in groups_with_time:
        by_weekday[group.weekday].append(group)

    visible_days = [
        (day_num, day_label)
        for day_num, day_label in WEEKDAYS
        if day_num < 5 or day_num in by_weekday
    ]

    svg_width = time_axis_w + len(visible_days) * col_w
    svg_height = header_h + time_padding + (max_time - min_time) * hour_px // 60 + time_padding

    time_ticks = [
        {
            "label": f"{t // 60:02d}:00",
            "y": header_h + time_padding + (t - min_time) * hour_px // 60,
        }
        for t in range(min_time, max_time + 1, 60)
    ]

    days = []
    for idx, (day_num, day_label) in enumerate(visible_days):
        col_x = time_axis_w + idx * col_w
        day_groups = by_weekday[day_num]

        lane_end_times = []
        lane_assignments = []
        for group in day_groups:
            start_min = group.start_time.hour * 60 + group.start_time.minute
            end_min = group.end_time.hour * 60 + group.end_time.minute
            placed = False
            for lane_idx, lane_end in enumerate(lane_end_times):
                if start_min >= lane_end:
                    lane_end_times[lane_idx] = end_min
                    lane_assignments.append(lane_idx)
                    placed = True
                    break
            if not placed:
                lane_end_times.append(end_min)
                lane_assignments.append(len(lane_end_times) - 1)

        num_lanes = max(len(lane_end_times), 1)
        lane_w = col_w // num_lanes

        groups_data = []
        for group, lane_idx in zip(day_groups, lane_assignments):
            start_min = group.start_time.hour * 60 + group.start_time.minute
            end_min = group.end_time.hour * 60 + group.end_time.minute
            block_h = max(24, (end_min - start_min) * hour_px // 60)
            block_y = header_h + time_padding + (start_min - min_time) * hour_px // 60
            block_x = col_x + lane_idx * lane_w
            max_chars = max(1, int((lane_w - 2 * padding - 4) / (font_size * 0.6)))
            name_lines = _wrap_text(str(group.name), max_chars)
            name_y = block_y + block_h // 2 - (len(name_lines) - 1) * line_height // 2
            groups_data.append(
                {
                    "group": group,
                    "x": block_x + padding,
                    "y": block_y + padding,
                    "width": lane_w - 2 * padding,
                    "height": block_h - 2 * padding,
                    "cx": block_x + lane_w // 2,
                    "name_lines": name_lines,
                    "name_y": name_y,
                    "line_height": line_height,
                }
            )
        days.append(
            {
                "label": str(day_label),
                "x": col_x,
                "header_cx": col_x + col_w // 2,
                "groups": groups_data,
            }
        )

    return {
        "width": svg_width,
        "height": svg_height,
        "time_axis_width": time_axis_w,
        "header_height": header_h,
        "header_mid_y": header_h // 2,
        "time_ticks": time_ticks,
        "days": days,
    }
