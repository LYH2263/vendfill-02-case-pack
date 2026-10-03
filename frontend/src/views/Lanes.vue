<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'

const rows = ref<any[]>([])
const refill = ref<any>(null)
const draft = ref<Record<number, string>>({})
const savingId = ref<number | null>(null)
const error = ref('')
const okMsg = ref('')

async function loadAll() {
  rows.value = await api('/lanes')
  refill.value = await api('/refills/latest?location_id=1')
  for (const r of rows.value) draft.value[r.id] = String(r.case_qty ?? 1)
}

function lineOf(laneId: number) {
  return refill.value?.lines?.find((l: any) => l.lane_id === laneId)
}

async function save(r: any) {
  error.value = ''
  okMsg.value = ''
  savingId.value = r.id
  const raw = (draft.value[r.id] ?? '').trim()
  const body = raw === '' ? { case_qty: null } : { case_qty: Number(raw) }
  try {
    if (raw !== '' && (!Number.isInteger(body.case_qty) || (body.case_qty as number) <= 0)) {
      // 与后端同一口径，先在本地挡住明显非法值；后端 400 仍会兜底回滚
      throw new Error('箱规必须为正整数（留空视为 1）')
    }
    const res = await api(`/lanes/${r.id}`, { method: 'PUT', body: JSON.stringify(body) })
    await loadAll()
    okMsg.value = `${r.slot_no} 箱规已保存为 ${res.case_qty}，最新补货单已按新箱规重写`
  } catch (e: any) {
    // 保存失败：字段与单据都已在后端整体回滚，重新拉取保证页面也是旧值
    await loadAll()
    let msg = e?.message || '保存失败'
    try { msg = JSON.parse(e.message).detail || msg } catch { /* 非 JSON 错误体 */ }
    error.value = `${r.slot_no} 保存被拒：${msg}；箱规与补货单均未改动`
  } finally {
    savingId.value = null
  }
}

onMounted(loadAll)
</script>

<template>
  <h1>货道格子</h1>
  <p class="sub">机面货道网格 · 每道登记箱规件数，保存即按同一倍数口径重写最新补货小票</p>

  <p v-if="error" class="badge badge-bad" style="font-size:0.78rem;padding:0.4rem 0.6rem">{{ error }}</p>
  <p v-if="okMsg" class="badge badge-ok" style="font-size:0.78rem;padding:0.4rem 0.6rem">{{ okMsg }}</p>

  <div class="vf-machine-layout">
    <div class="vf-slot-grid">
      <div v-for="r in rows" :key="r.id" class="vf-slot">
        <div class="vf-slot-no">{{ r.slot_no }}</div>
        <div class="vf-slot-sku">{{ r.sku_name }}</div>
        <div class="vf-slot-bar">
          <div
            class="vf-slot-fill"
            :class="{ 'vf-need': r.gap > 0 }"
            :style="{ width: Math.min(r.fill_pct, 100) + '%' }"
          />
        </div>
        <div class="vf-slot-meta">{{ r.stock }}/{{ r.capacity }} · 缺 {{ r.gap }}</div>
        <div class="vf-case-edit">
          <label>箱规
            <input
              v-model="draft[r.id]"
              type="number" min="1" step="1"
              :disabled="savingId === r.id"
              @keyup.enter="save(r)"
            />
          </label>
          <button class="vf-case-save" :disabled="savingId === r.id" @click="save(r)">存</button>
        </div>
        <div
          v-if="lineOf(r.id)"
          class="vf-slot-meta"
          :style="{ color: lineOf(r.id).fill_qty === 0 && r.gap > 0 ? '#ffc14a' : undefined }"
        >
          补 {{ lineOf(r.id).fill_qty }}
          <template v-if="r.gap > 0 && lineOf(r.id).fill_qty === 0">· 不足一箱</template>
        </div>
      </div>
    </div>

    <aside class="vf-receipt" v-if="refill">
      <h2>*** 最新补货单 ***</h2>
      <div class="vf-receipt-line" v-for="l in refill.lines" :key="l.lane_id">
        <span>{{ l.slot_no }} {{ l.sku_name }}
          <small v-if="l.status === 'need_fill' && l.fill_qty === 0" style="color:#a05a00">（不足一箱·待补）</small>
        </span>
        <span>x{{ l.fill_qty }}<small v-if="l.case_qty > 1"> /箱{{ l.case_qty }}</small></span>
      </div>
      <p class="muted" style="margin:0.75rem 0 0;font-size:0.72rem;color:#6a5e48;text-align:center">
        合计 {{ refill.total_fill }} 件 · 待补 {{ refill.need_fill_count }} 道 — 机面打印预览 —
      </p>
    </aside>
  </div>
</template>

<style scoped>
.vf-case-edit {
  display: flex; align-items: center; gap: 0.25rem;
  margin-top: 0.3rem; font-size: 0.62rem; color: var(--vf-dim);
}
.vf-case-edit input {
  width: 2.6rem; background: #0a0c10; color: var(--vf-text);
  border: 1px solid #3a4656; border-radius: 2px;
  font: inherit; font-size: 0.68rem; padding: 0.1rem 0.2rem;
}
.vf-case-save {
  background: var(--vf-led); color: #041208; border: none; border-radius: 2px;
  font-size: 0.62rem; font-weight: 800; padding: 0.15rem 0.4rem; cursor: pointer;
}
.vf-case-save:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
