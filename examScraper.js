const puppeteer = require('puppeteer-extra');
const fs = require('fs').promises;
const path = require('path');
const { PDFDocument } = require('pdf-lib');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');
const AdblockerPlugin = require('puppeteer-extra-plugin-adblocker');
const userPrefs = require('puppeteer-extra-plugin-user-preferences');
const fetch = (...args) => import('node-fetch').then(({default: fetch}) => fetch(...args));

// Configure plugins
puppeteer.use(StealthPlugin());
puppeteer.use(AdblockerPlugin({ blockTrackers: true }));
puppeteer.use(userPrefs({
    userPrefs: {
        download: {
            prompt_for_download: false,
            open_pdf_in_system_reader: true
        },
        plugins: {
            always_open_pdf_externally: true
        }
    }
}));

async function readSubjects() {
    console.log('Reading subjects from subjects.txt...');
    const data = await fs.readFile('subjects.txt', 'utf8');
    const subjects = data.split('\n')
        .filter(line => line.trim())
        .map(line => {
            const [code, name] = line.split(':');
            return { code: code.trim(), name: name.trim() };
        });
    console.log(`Found ${subjects.length} subjects to process`);
    return subjects;
}

async function mergePDFs(folderPath, outputPath) {
    try {
        console.log(`Starting PDF merge process for ${folderPath}`);
        const files = await fs.readdir(folderPath);
        console.log('All files in directory:', files);
        
        // Check for both .pdf and .PDF extensions and sort by creation time
        const pdfFiles = files
            .filter(file => file.toLowerCase().endsWith('.pdf'))
            .map(filename => ({
                filename,
                // Extract year from filename (e.g., "2023_2024" -> 2023)
                year: parseInt(filename.split('_')[0]),
                // Get full path for the file
                path: path.join(folderPath, filename)
            }))
            .sort((a, b) => {
                // Sort by year first
                if (a.year !== b.year) return b.year - a.year;
                // If years are same, sort by filename
                return a.filename.localeCompare(b.filename);
            });
        
        if (pdfFiles.length === 0) {
            console.log('⚠️ No PDFs found to merge');
            console.log('Files in directory:', files);
            return;
        }

        console.log('PDFs will be merged in this order:', pdfFiles.map(f => f.filename).join('\n'));
        const mergedPdf = await PDFDocument.create();

        for (const file of pdfFiles) {
            console.log(`Processing PDF: ${file.filename}`);
            try {
                const pdfBytes = await fs.readFile(file.path);
                const pdf = await PDFDocument.load(pdfBytes);
                const copiedPages = await mergedPdf.copyPages(pdf, pdf.getPageIndices());
                copiedPages.forEach((page) => mergedPdf.addPage(page));
                console.log(`✓ Added ${copiedPages.length} pages from ${file.filename}`);
            } catch (error) {
                console.error(`Error processing ${file.filename}:`, error);
                continue;
            }
        }

        console.log('Saving merged PDF...');
        const mergedPdfBytes = await mergedPdf.save();
        await fs.writeFile(outputPath, mergedPdfBytes);
        
        console.log(`✅ Successfully merged ${pdfFiles.length} PDFs into ${outputPath}`);
    } catch (error) {
        console.error('❌ Error merging PDFs:', error);
        throw error;
    }
}

async function downloadPDF(page, url, folderPath, index) {
    try {
        console.log(`Opening link in new tab: ${url}`);
        
        // Create a new tab
        const newPage = await page.browser().newPage();
        
        // Set download behavior using CDP
        await newPage._client().send('Page.setDownloadBehavior', {
            behavior: 'allow',
            downloadPath: path.resolve(folderPath)
        });

        // Navigate to URL and wait for download to start
        console.log('Navigating to URL...');
        await newPage.goto(url).catch(e => {
            // Ignore navigation errors as they're expected during PDF downloads
            if (!e.message.includes('net::ERR_ABORTED')) {
                throw e;
            }
        });

        // Wait for download to complete
        console.log('Waiting for download to complete...');
        await new Promise(resolve => setTimeout(resolve, 750));

        // Verify file was downloaded by checking directory
        const files = await fs.readdir(folderPath);
        const newFiles = files.filter(file => file.toLowerCase().endsWith('.pdf'));
        
        if (newFiles.length === 0) {
            throw new Error('No PDF file was downloaded');
        }
        
        console.log(`Found downloaded files: ${newFiles.join(', ')}`);

        // Close the tab
        await newPage.close();
        
        console.log(`✅ Download completed for URL: ${url}`);
        
        // Wait before next download
        await new Promise(resolve => setTimeout(resolve, 1000));
        
        return true;
        
    } catch (error) {
        console.error(`❌ Error downloading PDF: ${error.message}`);
        return false;
    }
}

let isFirstRun = true;

async function processSubject(browser, subject) {
    console.log(`\n=== Processing subject: ${subject.code} - ${subject.name} ===`);
    const page = await browser.newPage();
    const folderPath = path.join(__dirname, subject.name);
    console.log(`Creating directory: ${folderPath}`);
    await fs.mkdir(folderPath, { recursive: true });

    try {
        console.log('Navigating to search page...');
        await page.goto('https://regexam.nuigalway.ie/regexam/paper_index_search_main_menu.asp#');
        const waitTime = isFirstRun ? 27000 : 5000;
        console.log(`Waiting for page load (${waitTime/1000} seconds)...`);
        await new Promise(resolve => setTimeout(resolve, waitTime));
        isFirstRun = false;

        console.log('Looking for search frame...');
        const frames = await page.frames();
        const searchFrame = frames.find(frame => frame.name() === 'search_pane');
        
        if (!searchFrame) {
            throw new Error('Search frame not found');
        }
        console.log('✓ Found search frame');

        console.log(`Entering module code: ${subject.code}`);
        await searchFrame.waitForSelector('input[name="module"]');
        await searchFrame.type('input[name="module"]', subject.code);
        console.log('Clicking search button...');
        await searchFrame.click('input[type="submit"][value="Search"]');
        
        console.log('Waiting for results (3 seconds)...');
        await new Promise(resolve => setTimeout(resolve, 3000));

        console.log('Looking for results frame...');
        const resultsFrame = frames.find(frame => frame.name() === 'results_pane');
        
        if (!resultsFrame) {
            throw new Error('Results frame not found');
        }
        console.log('✓ Found results frame');

        console.log('Searching for exam paper links...');
        const rows = await resultsFrame.$$('tr[bgcolor="#E0F0F0"], tr[bgcolor="#C0F0F0"]');
        console.log(`Found ${rows.length} potential result rows`);
        
        let downloadIndex = 0;
        let successfulDownloads = 0;

        for (const row of rows) {
            const link = await row.$('a');
            if (link) {
                const href = await link.evaluate(el => el.href);
                if (href.includes('paper_index_download')) {
                    const success = await downloadPDF(page, href, folderPath, downloadIndex++);
                    if (success) {
                        successfulDownloads++;
                    }
                }
            }
        }
        console.log(`✅ Downloaded ${successfulDownloads} PDFs for ${subject.code}`);

        console.log('Starting PDF merge process...');
        const outputPath = path.join(__dirname, `${subject.name}.pdf`);
        await mergePDFs(folderPath, outputPath);
        
        console.log('Cleaning up temporary directory...');
        await fs.rmdir(folderPath, { recursive: true });
        console.log(`✅ Completed processing ${subject.code}\n`);

    } catch (error) {
        console.error(`❌ Error processing ${subject.code}:`, error);
    } finally {
        await page.close();
    }
}

async function main() {
    console.log('=== Starting Exam Paper Scraper ===\n');
    const subjects = await readSubjects();
    
    console.log('Launching browser...');
    const browser = await puppeteer.launch({
        headless: false,
        defaultViewport: null
    });
    console.log('✓ Browser launched');

    try {
        for (const subject of subjects) {
            await processSubject(browser, subject);
        }
    } finally {
        console.log('\nClosing browser...');
        await browser.close();
        console.log('✅ Process complete');
    }
}

main().catch(error => {
    console.error('❌ Fatal error:', error);
    process.exit(1);
}); 