import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 10000,
  headers: { 'Content-Type': 'application/json' },
})

export async function fetchArbSignals() {
  const { data } = await api.get('/signals/arb')
  return data
}

export async function fetchDiscordStances(marketId) {
  const { data } = await api.get('/signals/discord', { params: { market_id: marketId } })
  return data
}

export async function fetchMarketDetail(conditionId) {
  const { data } = await api.get(`/markets/${conditionId}`)
  return data
}

export async function fetchPipelineStatus() {
  const { data } = await api.get('/pipeline/status')
  return data
}

export async function fetchHealth() {
  const { data } = await api.get('/health')
  return data
}

export default api
