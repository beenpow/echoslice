import './App.css'
import YoutubeClipPlayer from './components/YoutubeClipPlayer'

function App() {

    return (
        <div>
          <h1>EchoSlice</h1>
            <YoutubeClipPlayer videoId="Ks-_Mh1QhMc" startSec={110} endSec={140} />
        </div>
    );
}

export default App;