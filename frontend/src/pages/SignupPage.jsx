import { useState } from 'react'
import styles from './SignupPage.module.css'
import { API_BASE_URL } from '../config/api';

const CATEGORIES = [
  { emoji: '💻', name: 'IT/테크', value: 'tech' },
  { emoji: '📈', name: '경제',   value: 'economy' },
  { emoji: '🌍', name: '국제',   value: 'world' },
  { emoji: '⚽', name: '스포츠', value: 'sports' },
  { emoji: '🎬', name: '연예',   value: 'entertainment' },
  { emoji: '🏛️', name: '정치',   value: 'politics' },
]

export default function SignupPage({ onSignup }) {
  const [email, setEmail] = useState('')
  const [selected, setSelected] = useState(['tech'])

  const toggleCategory = (value) => {
    setSelected(prev =>
      prev.includes(value)
        ? prev.filter(v => v !== value)
        : [...prev, value]
    )
  }

  const handleSubmit = async () => {
    if (!email) return alert('이메일을 입력해주세요')
    if (selected.length === 0) return alert('카테고리를 하나 이상 선택해주세요')

    try {
      const res = await fetch(`${API_BASE_URL}/subscribe`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, category: selected }),
      })
      const data = await res.json()

      if (res.status === 201) {
        onSignup && onSignup()
      } else if (res.status === 409) {
        const detail = data.detail || {}
        if (detail.verification_pending) {
          alert('이미 신청된 이메일입니다. 메일함에서 인증을 확인해주세요.')
        } else {
          alert('이미 구독 중인 이메일입니다.')
        }
        onGoMain && onGoMain()
      } else {
        alert('오류가 발생했습니다. 잠시 후 다시 시도해주세요.')
      }
    } catch {
      alert('네트워크 오류가 발생했습니다.')
    }
  }

  return (
    <div className={styles.wrap}>
      <div className={styles.eyebrow}>NewsFlow</div>
      <h1 className={styles.title}>
        나만의 <em>뉴스</em>를<br />매일 아침 받아보세요
      </h1>
      <p className={styles.sub}>
        관심 분야를 선택하면 매일 정해진 시간에<br />
        큐레이션된 뉴스를 이메일로 보내드립니다.
      </p>

      <div className={styles.fieldGroup}>
        <div className={styles.label}>이메일 주소</div>
        <input
          className={styles.input}
          type="email"
          placeholder="example@email.com"
          value={email}
          onChange={e => setEmail(e.target.value)}
        />
      </div>

      <div className={styles.label}>관심 카테고리 선택 (복수 선택 가능)</div>
      <div className={styles.grid}>
        {CATEGORIES.map(cat => (
          <div
            key={cat.value}
            className={`${styles.chip} ${selected.includes(cat.value) ? styles.selected : ''}`}
            onClick={() => toggleCategory(cat.value)}
          >
            <span className={styles.emoji}>{cat.emoji}</span>
            <span className={styles.chipName}>{cat.name}</span>
          </div>
        ))}
      </div>

      <button className={styles.btn} onClick={handleSubmit}>
        구독 시작하기
      </button>
      <p className={styles.note}>
        비밀번호 없이 이메일만으로 구독할 수 있어요<br />
        구독 취소 시 구독 정보가 삭제되며, 다시 구독하려면 이메일 인증이 필요합니다
      </p>
    </div>
  )
}