
import {BrowserRouter,Routes,Route} from 'react-router-dom'
import Admin from './Admin'
import Consulta from './Consulta'
export default ()=> (
  <BrowserRouter>
    <Routes>
      <Route path="/" element={<Consulta/>}/>
      <Route path="/admin" element={<Admin/>}/>
    </Routes>
  </BrowserRouter>
)
