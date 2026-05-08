/**
 * Chart theme presets — shared color palette with mermaid-renderer themes.
 */

export const CHART_THEMES = {
  corporate: {
    colors: ["#4A90D9", "#7EC8E3", "#48BB78", "#ED8936", "#9F7AEA", "#FC8181", "#76E4F7", "#F6E05E"],
    background: "#FFFFFF",
    textColor: "#2C3E50",
    gridColor: "#E2E8F0",
    fontFamily: '"Noto Sans CJK KR", "Pretendard", "Noto Sans KR", "Segoe UI", sans-serif',
  },
  modern: {
    colors: ["#6C5CE7", "#00CEC9", "#FD79A8", "#FDCB6E", "#55EFC4", "#E17055", "#74B9FF", "#A29BFE"],
    background: "#FFFFFF",
    textColor: "#2D3436",
    gridColor: "#DDD6FE",
    fontFamily: '"Noto Sans CJK KR", "Pretendard", "Inter", "Segoe UI", sans-serif',
  },
  warm: {
    colors: ["#E8725C", "#F0A868", "#6BBF7B", "#5B9BD5", "#C77DBA", "#F7DC6F", "#85C1E9", "#EB984E"],
    background: "#FFFFFF",
    textColor: "#3D2B1F",
    gridColor: "#F0D0B0",
    fontFamily: '"Noto Sans CJK KR", "Pretendard", "Noto Sans KR", "Georgia", serif',
  },
  dark: {
    colors: ["#6C5CE7", "#00CEC9", "#FD79A8", "#FDCB6E", "#55EFC4", "#E17055", "#74B9FF", "#A29BFE"],
    background: "#1A202C",
    textColor: "#E2E8F0",
    gridColor: "#4A5568",
    fontFamily: '"Noto Sans CJK KR", "Pretendard", "Inter", "Segoe UI", sans-serif',
  },
  minimal: {
    colors: ["#718096", "#A0AEC0", "#CBD5E0", "#E2E8F0", "#4A5568", "#2D3748", "#1A202C", "#F7FAFC"],
    background: "#FFFFFF",
    textColor: "#2D3748",
    gridColor: "#E2E8F0",
    fontFamily: '"Noto Sans CJK KR", "Pretendard", "Helvetica Neue", "Arial", sans-serif',
  },
};

export const DEFAULT_THEME = "corporate";
