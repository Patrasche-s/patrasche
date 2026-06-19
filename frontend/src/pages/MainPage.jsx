import { useEffect, useState } from 'react'
import { API_BASE_URL } from '../config/api'
import styles from './MainPage.module.css'

const TABS = [
  { emoji: '💻', name: 'IT/테크', value: 'tech' },
  { emoji: '📈', name: '경제',   value: 'economy' },
  { emoji: '🌍', name: '국제',   value: 'world' },
  { emoji: '⚽', name: '스포츠', value: 'sports' },
  { emoji: '🎬', name: '연예',   value: 'entertainment' },
  { emoji: '🏛️', name: '정치',   value: 'politics' },
]

// desc에서 URL 추출
function extractUrl(desc) {
  const match = desc?.match(/https?:\/\/[^\s]+/)
  return match ? match[0] : null
}

// "2026-05-20" → "5월 20일"
function formatBatchDate(dateStr) {
  if (!dateStr) return ''
  const [, m, d] = dateStr.split('-')
  return m && d ? `${Number(m)}월 ${Number(d)}일` : dateStr
}

export default function MainPage() {
  const [activeTab, setActiveTab] = useState('tech')
  const [news, setNews] = useState([])
  const [isLoading, setIsLoading] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')
  const [hasNews, setHasNews] = useState({})
  const [isFallback, setIsFallback] = useState(false)   
  const [batchDate, setBatchDate] = useState('')        

  useEffect(() => {
    setIsLoading(true)
    setErrorMessage('')

    fetch(`${API_BASE_URL}/api/news/list?category=${encodeURIComponent(activeTab)}`)
      .then(res => {
        if (!res.ok) throw new Error(`뉴스 조회 실패 (${res.status})`)
        return res.json()
      })
      .then(data => {
        const items = Array.isArray(data) ? data : data.items || []
        setNews(items)
        setIsFallback(Boolean(data.is_fallback))   // 추가
        setBatchDate(data.batch_date || '')        // 추가
        setHasNews(prev => ({ ...prev, [activeTab]: items.length > 0 }))
      })
      .catch(err => {
        console.error(err)
        setErrorMessage('뉴스를 불러오지 못했어요')
        setNews([])
        setIsFallback(false)                        // 추가
        setBatchDate('')                            // 추가
        setHasNews(prev => ({ ...prev, [activeTab]: false }))
      })
      .finally(() => setIsLoading(false))
  }, [activeTab])

  return (
    <div>
      <div className={styles.header}>
        <div className={styles.greeting}>오늘의 뉴스</div>
        <div className={styles.title}>
          좋은 아침이에요,<br /><em>큐레이션 뉴스</em>가 도착했어요
        </div>
      </div>

      <div className={styles.tabs}>
        {TABS.map(tab => (
          <button
            key={tab.value}
            className={`${styles.tab} ${activeTab === tab.value ? styles.active : ''}`}
            style={{ opacity: hasNews[tab.value] === false ? 0.4 : 1 }}
            onClick={() => setActiveTab(tab.value)}
          >
            {tab.emoji} {tab.name}
          </button>
        ))}
      </div>

      <div className={styles.list}>
        {isLoading ? (
          <div className={styles.empty}>
            <p>뉴스를 불러오는 중이에요</p>
          </div>
        ) : news.length === 0 ? (
          <div className={styles.empty}>
            <span>📭</span>
            <p>{errorMessage || '아직 뉴스가 없어요'}</p>
          </div>
        ) : (
          <>
          {isFallback && (
            <div className={styles.fallbackBadge}>
              🕐 {formatBatchDate(batchDate)} 배치예요. 오늘 뉴스는 준비 중이에요.
            </div>
          )}
          {news.map((item, i) => {
            const url = extractUrl(item.desc)
            return (
              <div
                key={i}
                className={styles.card}
                onClick={() => url && window.open(url, '_blank')}
                style={{ cursor: url ? 'pointer' : 'default' }}
              >
                <div className={styles.meta}>
                  <span className={styles.source}>{item.source}</span>
                  <span className={styles.dot} />
                  <span className={styles.time}>{item.time}</span>
                </div>
                <div className={styles.newsTitle}>{item.title}</div>
                <div className={styles.desc}>{item.desc}</div>
              </div>
            )
          })}
          </>
        )}
      </div>
    </div>
  )
}