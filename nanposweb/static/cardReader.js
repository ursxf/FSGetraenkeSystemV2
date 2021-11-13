let port;
let reader;
let inputDone;
let outputDone;
let inputStream;
let outputStream;

const buttonConnect = document.getElementById('connectReader');

document.addEventListener('DOMContentLoaded', () => {
  buttonConnect.addEventListener('click', clickConnect);
    // CODELAB: Add feature detection here.
    const notSupported = document.getElementById('notSupported');
    notSupported.classList.toggle('hidden', 'serial' in navigator);
});

/**
 * @name connect
 * Opens a Web Serial connection to a micro:bit and sets up the input and
 * output stream.
 */
async function connect() {
    // CODELAB: Add code to request & open port here.
    let filters = [
        { usbVendorId: 0x067B, usbProductId: 0x2303 },
    ];
    port = await navigator.serial.requestPort({ filters });
    await port.open({ baudRate: 115200 });

    // CODELAB: Add code setup the output stream here.

    // CODELAB: Send CTRL-C and turn off echo on REPL

    // CODELAB: Add code to read the stream here.
    let decoder = new TextDecoderStream();
    inputDone = port.readable.pipeTo(decoder.writable);
    inputStream = decoder.readable;

    reader = inputStream.getReader();
    readLoop();
}

/**
 * @name clickConnect
 * Click handler for the connect/disconnect button.
 */
async function clickConnect() {
    // CODELAB: Add disconnect code here.

    // CODELAB: Add connect code here.
    await connect();

    // CODELAB: Reset the grid on connect here.

    // CODELAB: Initialize micro:bit buttons.

    toggleUIConnected(true);
}

/**
 * @name readLoop
 * Reads data from the input stream and displays it on screen.
 */
async function readLoop() {
    // CODELAB: Add read loop here.
    while (true) {
      const { value, done } = await reader.read();
      if (value) {
        log.textContent += value + '\n';
      }
      if (done) {
        console.log('[readLoop] DONE', done);
        reader.releaseLock();
        break;
      }
    }
}

function toggleUIConnected(connected) {
  let lbl = 'Connect';
  if (connected) {
    lbl = 'Disconnect';
  }
  buttonConnect.textContent = lbl;
}
