# VendFill 售货机补货

按货道容量、库存与在途量计算缺口，再按每条货道登记的**箱规件数**向下取整生成补货单（非负、不超缺口）。

- 每条货道登记箱规件数（正整数）；箱规留空或 1 = 按件补，与现网一致；箱规 ≤ 0 直接打回。
- 口径只有一套（货道编辑 / 最新补货单 / 汇总共用 `fill_engine`）：可补量先按缺口封顶，再向下取整到箱规整数倍。
- 取整后为 0 则补量为 0，但只要物理缺口 > 0，状态仍是「待补」——「不足一整箱」与「已满仓」互斥。
- 在货道页改箱规并保存时，若点位已有最新补货单，会在**同一事务**里按新箱规重写该单全部行；任一步失败，箱规字段与单据整体回滚。历史补货单不动。

技术栈：Python 3.12 / FastAPI / SQLAlchemy / PostgreSQL / Vue 3 / TypeScript / Vite

## 启动

```bash
docker compose up --build
```

| 服务 | 地址 |
| --- | --- |
| 前端 | http://localhost:4800 |
| API | http://localhost:9800 |
| API 文档 | http://localhost:9800/docs |
| Postgres | localhost:5449 |

健康检查：`GET http://localhost:9800/api/health`

## 使用说明

1. 在「点位」「货道」查看售货机布局与库存。
2. 在「销量」了解近期出货。
3. 打开「补货单」按缺口生成建议补货量。
4. 在「满仓」「汇总」查看已满货道与补货合计。

## 开发与测试

```bash
docker compose exec api pytest -q
```
