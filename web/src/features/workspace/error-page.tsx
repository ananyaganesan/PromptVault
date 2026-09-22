import { Link } from 'react-router-dom'
import { Button } from '../../components/ui/prototype'
export function ErrorPage({ code }: { code: '403' | '404' }) { const forbidden = code === '403'; return <main className="error-main"><div><strong className="error-code">{code}</strong><h1>{forbidden ? 'Access restricted' : 'Page not found'}</h1><p>{forbidden ? "You don't have permission to access this resource." : "The page you're looking for doesn't exist or may have been moved."}</p><Link to="/dashboard"><Button>Return to dashboard</Button></Link></div></main> }
