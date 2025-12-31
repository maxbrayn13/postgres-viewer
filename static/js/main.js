// TenderFinder Commercial - Interactive Features

document.addEventListener('DOMContentLoaded', function() {
    
    // Fast filter form submission
    const filterForm = document.getElementById('filterForm');
    if (filterForm) {
        const inputs = filterForm.querySelectorAll('input, select');
        inputs.forEach(input => {
            input.addEventListener('change', function() {
                if (input.type === 'checkbox' || input.tagName === 'SELECT') {
                    filterForm.submit();
                }
            });
        });
        
        // Submit on Enter for text inputs
        filterForm.querySelectorAll('input[type="number"], input[type="search"]').forEach(input => {
            input.addEventListener('keypress', function(e) {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    filterForm.submit();
                }
            });
        });
    }
    
    // Country tabs
    const countryTabs = document.querySelectorAll('.country-tab');
    const countryPanels = document.querySelectorAll('.country-panel');
    
    countryTabs.forEach(tab => {
        tab.addEventListener('click', function() {
            const country = this.dataset.country;
            
            // Update active tab
            countryTabs.forEach(t => t.classList.remove('active'));
            this.classList.add('active');
            
            // Show corresponding panel
            countryPanels.forEach(panel => {
                if (panel.dataset.country === country) {
                    panel.style.display = 'block';
                } else {
                    panel.style.display = 'none';
                }
            });
        });
    });
    
    // Auto-hide alerts after 5 seconds
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(alert => {
        setTimeout(() => {
            alert.style.opacity = '0';
            alert.style.transition = 'opacity 0.5s';
            setTimeout(() => alert.remove(), 500);
        }, 5000);
    });
    
    // Deposit calculator
    const depositInput = document.getElementById('depositInput');
    const depositSlider = document.getElementById('depositSlider');
    
    if (depositInput && depositSlider) {
        depositSlider.addEventListener('input', function() {
            depositInput.value = this.value;
        });
        
        depositInput.addEventListener('input', function() {
            depositSlider.value = this.value;
        });
    }
    
    // Margin calculator
    const marginInput = document.getElementById('marginInput');
    const marginSlider = document.getElementById('marginSlider');
    
    if (marginInput && marginSlider) {
        marginSlider.addEventListener('input', function() {
            marginInput.value = this.value;
        });
        
        marginInput.addEventListener('input', function() {
            marginSlider.value = this.value;
        });
    }
    
    // Price formatter
    function formatPrice(price) {
        return new Intl.NumberFormat('ru-RU', {
            style: 'currency',
            currency: 'KZT',
            minimumFractionDigits: 0
        }).format(price);
    }
    
    // Product price calculation
    const productPrices = document.querySelectorAll('[data-product-price]');
    productPrices.forEach(element => {
        const price = parseFloat(element.dataset.productPrice);
        const quantity = parseFloat(element.dataset.quantity || 1);
        const total = price * quantity;
        
        const totalElement = element.parentElement.querySelector('.product-total');
        if (totalElement) {
            totalElement.textContent = formatPrice(total);
        }
    });
    
    // Lazy loading for images
    const images = document.querySelectorAll('img[data-src]');
    const imageObserver = new IntersectionObserver((entries, observer) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const img = entry.target;
                img.src = img.dataset.src;
                img.removeAttribute('data-src');
                observer.unobserve(img);
            }
        });
    });
    
    images.forEach(img => imageObserver.observe(img));
    
    // Confirm before delete
    const deleteButtons = document.querySelectorAll('[data-confirm]');
    deleteButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            const message = this.dataset.confirm || 'Вы уверены?';
            if (!confirm(message)) {
                e.preventDefault();
            }
        });
    });
    
    // Loading indicator
    const forms = document.querySelectorAll('form[data-loading]');
    forms.forEach(form => {
        form.addEventListener('submit', function() {
            const button = form.querySelector('button[type="submit"]');
            if (button) {
                button.disabled = true;
                button.innerHTML = '<span class="spinner"></span> Загрузка...';
            }
        });
    });
    
    // Copy to clipboard
    const copyButtons = document.querySelectorAll('[data-copy]');
    copyButtons.forEach(button => {
        button.addEventListener('click', function() {
            const text = this.dataset.copy;
            navigator.clipboard.writeText(text).then(() => {
                const original = this.textContent;
                this.textContent = '✓ Скопировано!';
                setTimeout(() => {
                    this.textContent = original;
                }, 2000);
            });
        });
    });
    
    // Stats animation
    const stats = document.querySelectorAll('.stat-value');
    const statsObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const target = parseFloat(entry.target.textContent.replace(/[^0-9]/g, ''));
                animateNumber(entry.target, 0, target, 1000);
                statsObserver.unobserve(entry.target);
            }
        });
    });
    
    stats.forEach(stat => statsObserver.observe(stat));
    
    function animateNumber(element, start, end, duration) {
        const startTime = performance.now();
        
        function update(currentTime) {
            const elapsed = currentTime - startTime;
            const progress = Math.min(elapsed / duration, 1);
            
            const current = Math.floor(start + (end - start) * progress);
            element.textContent = current.toLocaleString('ru-RU');
            
            if (progress < 1) {
                requestAnimationFrame(update);
            }
        }
        
        requestAnimationFrame(update);
    }
    
    // Search highlight
    const searchInput = document.getElementById('searchInput');
    if (searchInput) {
        const searchTerm = searchInput.value.toLowerCase();
        if (searchTerm) {
            const lotTitles = document.querySelectorAll('.lot-title');
            lotTitles.forEach(title => {
                const text = title.textContent;
                const index = text.toLowerCase().indexOf(searchTerm);
                if (index >= 0) {
                    const before = text.substring(0, index);
                    const match = text.substring(index, index + searchTerm.length);
                    const after = text.substring(index + searchTerm.length);
                    title.innerHTML = before + '<mark style="background: yellow; padding: 2px;">' + match + '</mark>' + after;
                }
            });
        }
    }
});

// Service Worker for offline support (optional)
if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
        navigator.serviceWorker.register('/static/sw.js')
            .then(reg => console.log('Service Worker registered'))
            .catch(err => console.log('Service Worker registration failed'));
    });
}
