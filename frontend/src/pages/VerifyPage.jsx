import { useEffect, useState } from 'react'
import { API_BASE_URL } from '../config/api'

export default function VerifyPage({ onGoMain }) {
  const [status, setStatus] = useState('loading') // loading | success | already | fail

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const email = params.get('email')
    const token = params.get('token')

    if (!email || !token) {
      setStatus('fail')
      return
    }

    fetch(`${API_BASE_URL}/verify?email=${encodeURIComponent(email)}&token=${encodeURIComponent(token)}`)
      .then(res => {
        if (res.ok) return res.json().then(() => setStatus('success'))
        if (res.status === 400) return setStatus('fail')
        if (res.status === 404) return setStatus('fail')
        setStatus('fail')
      })
      .catch(() => setStatus('fail'))
  }, [])

  const content = {
    loading: { icon: '⏳', title: '인증 확인 중...', desc: '잠시만 기다려주세요.' },
    success: { icon: '✅', title: '인증이 완료되었습니다!', desc: '이제 매일 아침 큐레이션 뉴스를 받아볼 수 있어요.' },
    already: { icon: '✅', title: '이미 인증된 이메일입니다', desc: '이미 인증이 완료된 계정이에요.' },
    fail:    { icon: '❌', title: '인증에 실패했습니다', desc: '링크가 유효하지 않거나 만료되었어요. 다시 구독 신청해주세요.' },
  }[status]

  return (
    <div style={{ textAlign: 'center', padding: '60px 24px' }}>
      <p style={{ fontSize: '48px' }}>{content.icon}</p>
      <h2 style={{ marginTop: '16px', color: 'var(--text)' }}>{content.title}</h2>
      <p style={{ color: 'var(--text2)', marginTop: '12px', lineHeight: 1.6 }}>{content.desc}</p>
      {status !== 'loading' && (
        <button
          onClick={onGoMain}
          style={{ marginTop: '32px', padding: '12px 24px', cursor: 'pointer',
            background: 'var(--accent)', border: 'none', borderRadius: '10px',
            fontFamily: 'inherit', fontSize: '14px', fontWeight: 600, color: '#0f0f0f' }}
        >
          뉴스 보러가기
        </button>
      )}
    </div>
  )
}