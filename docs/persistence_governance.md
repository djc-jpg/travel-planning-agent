# Persistence 治理（迁移 / 备份恢复 / 演练）

## 迁移机制
- 迁移文件：`app/persistence/migrations/*.sql`
- 执行器：`app/persistence/migration_runner.py`
- 命令：
```powershell
python -m app.persistence.migrate --db data/trip_agent.sqlite3
```

迁移状态记录在 `schema_migrations` 表中，支持幂等重复执行。

## 备份
```powershell
python -m app.persistence.backup --source-db data/trip_agent.sqlite3
```
默认输出到 `data/backups/`。

## 恢复
```powershell
python -m app.persistence.restore --backup-path data/backups/<backup_file>.sqlite3 --target-db data/trip_agent.sqlite3
```

## 故障演练
```powershell
.\scripts\persistence-drill.ps1
```

演练流程：
1. 写入基线标记；
2. 执行备份；
3. 模拟数据破坏；
4. 执行恢复；
5. 校验标记恢复。

演练报告输出：`eval/reports/persistence_drill_latest.json`。
