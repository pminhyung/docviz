# First Push to docviz Repository

워크스페이스에 모든 파일이 준비되었습니다. 사용자 터미널(Windows PowerShell 또는 Git Bash)에서 다음 명령을 순서대로 실행하면 docviz 저장소에 첫 push 됩니다.

## Prerequisite

- Git 설치되어 있어야 함
- GitHub 계정 인증 (HTTPS personal access token 또는 SSH key) 설정되어 있어야 함
- `https://github.com/pminhyung/docviz.git` 저장소가 GitHub에 미리 생성되어 있어야 함 (비어있어도 됨)

## Commands

PowerShell 기준:

```powershell
cd D:\Downloads\visubench\visubench

# 기존에 시도되었으나 실패한 .git 디렉토리 정리 (있다면)
Remove-Item -Recurse -Force .git -ErrorAction SilentlyContinue

# Git 초기화
git init -b main

# 본인 정보 설정 (글로벌 설정이 이미 있으면 생략 가능)
git config user.email "your-email@example.com"
git config user.name "Your Name"

# 모든 파일 staging
git add .

# 첫 커밋
git commit -m "Initial: paper master spec, Week 0 action guide, repo scaffolding"

# 원격 추가 + push
git remote add origin https://github.com/pminhyung/docviz.git
git push -u origin main
```

Git Bash 또는 macOS/Linux:

```bash
cd /d/Downloads/visubench/visubench  # Git Bash
# 또는
cd ~/path/to/visubench  # 본인 환경에 맞게

rm -rf .git
git init -b main
git config user.email "your-email@example.com"
git config user.name "Your Name"
git add .
git commit -m "Initial: paper master spec, Week 0 action guide, repo scaffolding"
git remote add origin https://github.com/pminhyung/docviz.git
git push -u origin main
```

## Verification

성공하면 GitHub `https://github.com/pminhyung/docviz` 페이지에서 다음 파일이 보여야 합니다:

- `README.md`
- `PAPER_MASTER_SPEC.md`
- `QG-MDV_Week0_Action_Guide.md`
- `.gitignore`
- `.github/pull_request_template.md`

## After Push

연구 agent가 다른 환경에서 작업할 때 사용할 명령:

```bash
git clone https://github.com/pminhyung/docviz.git
cd docviz
# 작업 시작 시:
git checkout -b feat/week0-bundles  # 예시 feature branch
# 작업 후:
git add . && git commit -m "Day 1: HotpotQA bundle loader" && git push -u origin feat/week0-bundles
# GitHub UI에서 PR 열면 advisor가 review
```

## Workflow recap

1. 연구 agent가 feature branch에서 작업 → push
2. PR 생성 (template 자동 적용됨)
3. Advisor가 `git fetch && git diff origin/main..origin/<branch>` 로 변경 검토
4. 코드/데이터/결과 기반 피드백
5. Approve / request changes
6. main에 merge

각 weekly milestone마다 `docs/weekly_reports/WEEK<N>_REPORT.md` 작성을 잊지 말 것 (master spec §17.4 참조).
