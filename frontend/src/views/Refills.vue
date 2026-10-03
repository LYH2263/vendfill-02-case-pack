<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
const data = ref<any>(null)
async function run() { data.value = await api('/refills/run?location_id=1', { method: 'POST' }) }
onMounted(run)
</script>
<template>
  <h1>补货小票</h1>
  <p class="sub">先按缺口封顶，再向下取整到箱规整数倍 · 不足一箱仍挂待补，不算满仓</p>
  <button class="btn" @click="run">生成补货单</button>
  <div style="margin-top:1rem" v-if="data">
    <div class="vf-receipt">
      <h2>*** VendFill 补货单 ***</h2>
      <div class="vf-receipt-line" style="font-weight:700;border-bottom:2px dashed #8a7e64">
        <span>货道 / 商品</span><span>补量 / 箱规</span>
      </div>
      <div class="vf-receipt-line" v-for="l in data.lines" :key="l.lane_id">
        <span>{{ l.slot_no }} {{ l.sku_name }}
          <small v-if="l.status === 'need_fill' && l.fill_qty === 0" style="color:#a05a00">（不足一箱·待补）</small>
          <small v-else-if="l.status === 'need_fill'">（待补）</small>
          <small v-else-if="l.status === 'full'">（满仓）</small>
          <small v-else>（超占）</small>
        </span>
        <span>{{ l.fill_qty }} / 缺{{ l.gap }}<small v-if="l.case_qty > 1"> · ×{{ l.case_qty }}/箱</small></span>
      </div>
      <p style="text-align:center;margin:1rem 0 0;font-size:0.72rem;color:#6a5e48">
        合计 {{ data.total_fill }} 件 · 待补 {{ data.need_fill_count }} 道 · 谢谢核对后装机
      </p>
    </div>
  </div>
</template>
