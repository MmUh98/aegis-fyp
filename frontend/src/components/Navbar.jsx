import { useEffect, useState } from 'react'
import { ethers } from 'ethers'
import { ShieldCheck, Wallet } from 'lucide-react'

const AMOY_CHAIN_ID = '0x13882'

export default function Navbar({ activeTab, setActiveTab, account, setAccount }) {
  const [connecting, setConnecting] = useState(false)
  const [chainId, setChainId] = useState(null)
  const [walletError, setWalletError] = useState(null)

  useEffect(() => {
    if (!window.ethereum) return undefined
    const onAccounts = (accounts) => setAccount(accounts[0] ?? null)
    const onChain = (id) => setChainId(id)
    window.ethereum.on('accountsChanged', onAccounts)
    window.ethereum.on('chainChanged', onChain)
    return () => {
      window.ethereum.removeListener('accountsChanged', onAccounts)
      window.ethereum.removeListener('chainChanged', onChain)
    }
  }, [setAccount])

  const connectWallet = async () => {
    setWalletError(null)
    if (!window.ethereum) {
      setWalletError('MetaMask not found. Install it to connect a wallet.')
      return
    }
    try {
      setConnecting(true)
      const provider = new ethers.BrowserProvider(window.ethereum)
      const accounts = await provider.send('eth_requestAccounts', [])
      setAccount(accounts[0] ?? null)
      setChainId(await provider.send('eth_chainId', []))
    } catch (error) {
      setWalletError(error?.code === 4001 ? 'Connection request was rejected.' : 'Wallet connection failed.')
    } finally {
      setConnecting(false)
    }
  }

  const wrongChain = account && chainId && chainId.toLowerCase() !== AMOY_CHAIN_ID
  const tabClass = (tab) => `rounded-lg px-3 py-2 text-sm font-medium transition ${
    activeTab === tab ? 'bg-slate-800 text-cyan-300 shadow-sm' : 'text-slate-400 hover:text-slate-100'
  }`

  return (
    <header className="sticky top-0 z-50 border-b border-slate-800/80 bg-slate-950/90 px-4 py-4 backdrop-blur-xl sm:px-8">
      <nav className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4" aria-label="Primary navigation">
        <button type="button" className="flex items-center gap-3" onClick={() => setActiveTab('verify')} aria-label="Aegis home">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl border border-cyan-300/30 bg-cyan-300/10 text-cyan-200">
            <ShieldCheck className="h-5 w-5" />
          </span>
          <span className="text-left">
            <span className="block font-display text-lg font-bold tracking-[0.18em] text-slate-100">AEGIS</span>
            <span className="block font-mono text-[10px] tracking-[0.2em] text-slate-500">PROVENANCE V2</span>
          </span>
        </button>

        <div className="order-3 flex w-full justify-center rounded-xl border border-slate-800 bg-slate-900/70 p-1 sm:order-2 sm:w-auto">
          <button type="button" onClick={() => setActiveTab('verify')} className={tabClass('verify')}>Verify Provenance</button>
          <button type="button" onClick={() => setActiveTab('register')} className={tabClass('register')}>Register Media</button>
        </div>

        <div className="order-2 flex flex-col items-end sm:order-3">
          <button
            type="button"
            onClick={connectWallet}
            disabled={connecting}
            title="Optional: registration is signed by the backend wallet."
            className="flex items-center gap-2 rounded-xl border border-slate-700 bg-slate-900 px-3 py-2 text-sm font-medium text-slate-200 transition hover:border-cyan-300/40 hover:bg-slate-800 disabled:opacity-60"
          >
            <Wallet className="h-4 w-4 text-cyan-300" />
            <span>{account ? `${account.slice(0, 6)}...${account.slice(-4)}` : connecting ? 'Connecting...' : 'Wallet (optional)'}</span>
          </button>
          {wrongChain && <span className="mt-1 text-[11px] text-amber-300">Switch to Polygon Amoy (80002)</span>}
          {walletError && <span className="mt-1 max-w-52 text-right text-[11px] text-rose-300">{walletError}</span>}
        </div>
      </nav>
    </header>
  )
}
