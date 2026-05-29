import { useEffect, useState } from 'react'
import { API_BASE_URL } from '../config/api'
import styles from './MainPage.module.css'

const TABS = [
  { emoji: '💻', name: 'IT/테크', value: 'tech' },
  { emoji: '📈', name: '경제',   value: 'economy' },
  { emoji: '🌍', name: '국제',   value: 'world' },
  { emoji: '⚽', name: '스포츠', value: 'sports' },
]

export default function MainPage() {
  const [activeTab, setActiveTab] = useState('tech') 
  const [news, setNews] = useState([])
  const [isLoading, setIsLoading] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')

  useEffect(()=> {
    setIsLoading(true)
    setErrorMessage('')

    fetch(`${API_BASE_URL}/api/news/list?category=${encodeURIComponent(activeTab)}`)
      .then(res => {
        if (!res.ok) {
          throw new Error(`뉴스 조회 실패 (${res.status})`)
        }
        return res.json()
      })
      .then(data => {
        const items = Array.isArray(data) ? data : data.items || []
        setNews(items)
      })
      .catch(err => {
        console.error(err)
        setErrorMessage('뉴스를 불러오지 못했어요')
        setNews([])
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
          news.map((item, i) => (
            <div key={i} className={styles.card}>
              <div className={styles.meta}>
                <span className={styles.source}>{item.source}</span>
                <span className={styles.dot} />
                <span className={styles.time}>{item.time}</span>
              </div>
              <div className={styles.newsTitle}>{item.title}</div>
              <div className={styles.desc}>{item.desc}</div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
