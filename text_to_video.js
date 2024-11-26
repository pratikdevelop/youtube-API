const puppeteer = require('puppeteer');
const fs = require('fs');
const ffmpeg = require('fluent-ffmpeg');

async function createImageWithText(text, outputFile) {
  const browser = await puppeteer.launch();
  const page = await browser.newPage();
  await page.setContent(`<html><body style="font-size:24px;color:white;background:black;text-align:center;display:flex;align-items:center;justify-content:center;height:100vh;">${text}</body></html>`);
  const screenshot = await page.screenshot();
  fs.writeFileSync(outputFile, screenshot);
  await browser.close();
  console.log('Image created with text');
}

function imagesToVideo(images, outputFile) {
  ffmpeg()
    .addInput('image-%d.png') // Your sequence of images
    .inputFPS(1) // One frame per second
    .output(outputFile)
    .on('end', () => {
      console.log('Video created from images');
    })
    .run();
}

// Example usage
(async () => {
  await createImageWithText('Hello World!', 'image-1.png');
  imagesToVideo(['image-1.png'], 'output.mp4');
})();
