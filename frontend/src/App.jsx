import { useState } from 'react'
import Navbar from './components/Navbar'
import RegisterView from './components/RegisterView'
import VerifyView from './components/VerifyView'

export default function App() {
  const [activeTab, setActiveTab] = useState('verify')
  const [account, setAccount] = useState(null)

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <Navbar activeTab={activeTab} setActiveTab={setActiveTab} account={account} setAccount={setAccount} />
      <main>{activeTab === 'verify' ? <VerifyView /> : <RegisterView />}</main>
    </div>
  )
}
