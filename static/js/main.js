
document.addEventListener('DOMContentLoaded', function() {
    const flashMessages = document.querySelectorAll('.flash');
    
    flashMessages.forEach(function(flash) {
        setTimeout(function() {
            flash.style.animation = 'slideOut 0.3s ease forwards';
            setTimeout(function() {
                flash.remove();
            }, 300);
        }, 5000);
    });

   
    const scoreBars = document.querySelectorAll('.ai-score-bar-fill');
    scoreBars.forEach(function(bar) {
        const width = bar.getAttribute('data-width');
        if (width) {
            
            requestAnimationFrame(function() {
                bar.style.width = width + '%';
            });
        }
    });
});



const style = document.createElement('style');
style.textContent = `
    @keyframes slideOut {
        from {
            transform: translateX(0);
            opacity: 1;
        }
        to {
            transform: translateX(400px);
            opacity: 0;
        }
    }
`;
document.head.appendChild(style);


document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
        e.preventDefault();
        const target = document.querySelector(this.getAttribute('href'));
        if (target) {
            target.scrollIntoView({
                behavior: 'smooth',
                block: 'start'
            });
        }
    });
});


document.querySelectorAll('form').forEach(form => {
    form.addEventListener('submit', function(e) {
        const submitBtn = this.querySelector('button[type="submit"]');
        if (submitBtn && !submitBtn.disabled) {
            submitBtn.disabled = true;
            submitBtn.style.opacity = '0.6';
            submitBtn.innerHTML = '<span style="display: inline-flex; align-items: center; gap: 8px;"><span style="display: inline-block; width: 14px; height: 14px; border: 2px solid white; border-top-color: transparent; border-radius: 50%; animation: spin 0.6s linear infinite;"></span> Processing...</span>';
            
          
            if (!document.getElementById('spin-animation')) {
                const spinStyle = document.createElement('style');
                spinStyle.id = 'spin-animation';
                spinStyle.textContent = `
                    @keyframes spin {
                        to { transform: rotate(360deg); }
                    }
                `;
                document.head.appendChild(spinStyle);
            }
        }
    });
});


document.querySelectorAll('select[name="status"]').forEach(select => {
    const originalValue = select.value;
    select.addEventListener('change', function() {
        const newValue = this.value;
        if ((originalValue === 'pending' || originalValue === 'under_review') && newValue === 'rejected') {
            if (!confirm('Are you sure you want to reject this application? The student will be notified.')) {
                this.value = originalValue;
            }
        }
    });
});


document.querySelectorAll('.card').forEach(card => {
    card.addEventListener('mouseenter', function() {
        this.style.transition = 'all 0.3s ease';
    });
});

console.log('CampusHire initialized successfully! 🎓');