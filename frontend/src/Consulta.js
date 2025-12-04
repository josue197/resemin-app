
import {useState} from 'react'
const API = "http://localhost:8000"
export default function(){
 const [dni,setDni]=useState("")
 const [fecha,setFecha]=useState("")
 const [res,setRes]=useState([])
 async function enviar(){
  const r=await fetch(API+"/consulta",{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify({dni,fecha})})
  const d=await r.json(); setRes(d.results)
 }
 return(<div>
  <h2>Consulta</h2>
  <input placeholder="DNI" onChange={e=>setDni(e.target.value)}/>
  <input placeholder="Fecha" onChange={e=>setFecha(e.target.value)}/>
  <button onClick={enviar}>Consultar</button>
  {res.map(r=><pre>{JSON.stringify(r,null,2)}</pre>)}
 </div>)
}
