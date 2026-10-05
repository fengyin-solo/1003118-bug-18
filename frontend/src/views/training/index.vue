<template>
  <section class="page" data-module="training">
    <header class="page-head">
      <div>
        <h2>安全培训管理</h2>
        <p class="page-desc">维护培训记录，围绕培训编号、培训主题、培训对象、培训日期做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记培训记录</button>
        <button class="btn" type="button" @click="exportRows">导出安全培训清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="search">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <label class="filter-item">
        <span>培训状态</span>
        <select v-model="statusFilter">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无安全培训数据，可先登记培训记录</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条安全培训记录</span>
      <span class="pager">
        <button class="btn ghost" type="button" :disabled="page <= 1" @click="goPage(-1)">上一页</button>
        <span>第 {{ page }} / {{ pageCount }} 页</span>
        <button class="btn ghost" type="button" :disabled="page >= pageCount" @click="goPage(1)">下一页</button>
      </span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/training'
const columns = ["培训编号", "培训主题", "培训对象", "培训日期", "培训讲师", "考核方式", "考核结果", "培训状态", "归档日期"]
const actions = ["组织培训", "组织考核", "归档"]
const statuses = ["待培训", "培训中", "已考核", "已归档"]
const stats = [{"label": "待培训人数", "value": 0}, {"label": "已考核人数", "value": 0}, {"label": "合格率", "value": 0}]

const rows = ref<Row[]>([])
const total = ref(0)
const page = ref(1)
const size = ref(20)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = ["考核结果", "培训对象", "培训日期"]
const statusFilter = ref('')

const pageCount = computed(() => Math.max(1, Math.ceil(total.value / size.value)))

function search() {
  page.value = 1
  void reload()
}

function resetFilters() {
  filters.value = {}
  statusFilter.value = ''
  page.value = 1
  void reload()
}

function goPage(delta: number) {
  // 翻页时检索条件留住，只在当前结果范围内移动页码
  page.value = Math.min(Math.max(1, page.value + delta), pageCount.value)
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '培训记录登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    if (!response.ok) {
      throw new Error('安全培训动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '安全培训操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const params = new URLSearchParams()
  for (const [field, value] of Object.entries(filters.value)) {
    if (value) {
      params.set(field, value)
    }
  }
  if (statusFilter.value) {
    params.set('status', statusFilter.value)
  }
  params.set('page', String(page.value))
  params.set('size', String(size.value))
  try {
    const response = await request(`${ENDPOINT}?${params.toString()}`)
    if (!response.ok) {
      throw new Error('培训记录列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '安全培训列表读取失败'
  }
}

onMounted(reload)
</script>
