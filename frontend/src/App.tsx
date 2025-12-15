import './App.css'
import YoutubeClipPlayer from './components/YoutubeClipPlayer'

function App() {

    return (
        <div>
          <h1>EchoSlice</h1>
            <YoutubeClipPlayer videoId="dQw4w9WgXcQ" startSec={30} endSec={45} />
        </div>
    );
}

export default App;