"""主进程内置定时器：服务器挂着就行，量化计算自动跑。

设计要点（为什么用"每次起子进程"而不是进程内直调）：
1. 随时迭代——每次任务都执行磁盘上的最新代码，服务器 git pull 之后
   下一次定时任务自动生效，Web 服务无需重启
2. 进程隔离——任务崩溃/内存膨胀不影响看板主进程，2C2G 上尤为重要
3. 与手动 CLI 完全同路径：python main.py news --collect / paper --refresh，
   手动验证过的行为和定时跑的一字不差

默认计划（周一至周五，Asia/Shanghai，可用 .env 覆盖）：
    18:10  news  --collect        采集电报+DeepSeek打分（收盘数据已更新）
    18:30  paper --refresh        模拟盘补账+结算
关闭方式：.env 里加 DISABLE_SCHEDULER=1
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "logs"
LOG_FILE = LOG_DIR / "scheduler.log"

# 任务名 → CLI 参数（与手动命令完全一致）
JOBS = {
    "news": ["news", "--collect"],
    "paper": ["paper", "--refresh"],
}
DEFAULT_TIMES = {"news": "18:10", "paper": "18:30"}

# 运行状态（进程内存，重启后清空；持久轨迹看 logs/scheduler.log）
_last_run: dict[str, dict] = {}
_scheduler = None


def _log(msg: str) -> None:
    LOG_DIR.mkdir(exist_ok=True)
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def run_job(name: str) -> None:
    """以子进程执行一个任务并记录结果（定时触发与手动测试共用此入口）。"""
    args = JOBS[name]
    t0 = datetime.now()
    _log(f"▶ {name} 开始: python main.py {' '.join(args)}")
    try:
        proc = subprocess.run(
            [sys.executable, str(ROOT / "main.py"), *args],
            cwd=str(ROOT), capture_output=True, text=True,
            timeout=1800,   # 30分钟护栏：卡死的任务按失败处理
        )
        ok = proc.returncode == 0
        tail = (proc.stdout or "").strip().splitlines()[-3:]
        _last_run[name] = {"at": t0.strftime("%Y-%m-%d %H:%M"),
                           "ok": ok, "seconds": round((datetime.now() - t0).total_seconds(), 1),
                           "tail": " | ".join(tail)[:300]}
        _log(f"{'✔' if ok else '✘'} {name} 结束: {_last_run[name]['seconds']}s "
             f"{' '.join(tail)[-200:]}")
    except Exception as e:  # noqa: BLE001 - 定时任务失败只记录，不抛出
        _last_run[name] = {"at": t0.strftime("%Y-%m-%d %H:%M"), "ok": False,
                           "seconds": round((datetime.now() - t0).total_seconds(), 1),
                           "tail": str(e)[:300]}
        _log(f"✘ {name} 异常: {e}")


def _cron_time(name: str) -> tuple[int, int]:
    hhmm = os.environ.get(f"{name.upper()}_TIME", DEFAULT_TIMES[name])
    hh, mm = hhmm.split(":")
    return int(hh), int(mm)


def start_scheduler():
    """启动内置定时器（幂等）。返回 scheduler；被禁用时返回 None。"""
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    if os.environ.get("DISABLE_SCHEDULER", "").strip() == "1":
        _log("内置定时器已通过 DISABLE_SCHEDULER=1 关闭")
        return None

    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger

    sched = BackgroundScheduler(timezone="Asia/Shanghai")
    for name in JOBS:
        hh, mm = _cron_time(name)
        sched.add_job(
            run_job, CronTrigger(day_of_week="mon-fri", hour=hh, minute=mm,
                                 timezone="Asia/Shanghai"),
            args=[name], id=name, name=name,
            max_instances=1, coalesce=True,   # 错过的合并为一次，不追赶多轮
        )
    sched.start()
    _scheduler = sched
    _log(f"内置定时器启动: " + ", ".join(
        f"{n} 周一至五 {DEFAULT_TIMES[n] if not os.environ.get(n.upper()+'_TIME') else os.environ[n.upper()+'_TIME']}"
        for n in JOBS))
    return sched


def status() -> dict:
    """定时器状态（供 /api/scheduler 与驾驶舱展示）。"""
    jobs = []
    if _scheduler is not None:
        for name in JOBS:
            job = _scheduler.get_job(name)
            jobs.append({
                "name": name,
                "trigger": str(job.trigger) if job else "",
                "next_run": job.next_run_time.strftime("%m-%d %H:%M") if job and job.next_run_time else None,
                "last": _last_run.get(name),
            })
    return {"enabled": _scheduler is not None, "timezone": "Asia/Shanghai", "jobs": jobs}
