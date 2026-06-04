import { useState } from 'react'
import SignupPage from './pages/SignupPage'
import MainPage from './pages/MainPage'
import './index.css'

export default function App() {
  // 'signup' | 'pending' | 'main'
  const [page, setPage] = useState('signup')

  return (
    <div style={{ maxWidth: '480px', margin: '0 auto', minHeight: '100vh' }}>
      {page === 'signup' && (
        <SignupPage onSignup={() => setPage('pending')} />
      )}
      {page === 'pending' && (
        <div style={{ textAlign: 'center', padding: '60px 24px' }}>
          <p style={{ fontSize: '48px' }}>📧</p>
          <h2>인증 메일을 확인해주세요</h2>
          <p style={{ color: '#888', marginTop: '12px' }}>
            입력하신 이메일로 인증 링크를 보냈어요.<br />
            메일함에서 인증을 완료하면 뉴스를 받아볼 수 있어요.
          </p>
          <button
            onClick={() => setPage('main')}
            style={{ marginTop: '32px', padding: '12px 24px', cursor: 'pointer' }}
          >
            뉴스 미리보기
          </button>
        </div>
      )}
      {page === 'main' && (
        <MainPage />
      )}
    </div>
  )
}