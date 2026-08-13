document.addEventListener('DOMContentLoaded', () => {
    const productsGrid = document.getElementById('productsGrid');
    const productCount = document.getElementById('productCount');
    const searchInput = document.getElementById('searchInput');
    const searchBtn = document.getElementById('searchBtn');

    let allProducts = [];

    // Fetch products from backend
    async function fetchProducts() {
        try {
            const response = await fetch('/api/products');
            if (!response.ok) throw new Error('API yanıt vermedi');
            
            allProducts = await response.json();
            renderProducts(allProducts);
        } catch (error) {
            console.error('Ürünler yüklenirken hata oluştu:', error);
            productsGrid.innerHTML = '<p style="text-align:center; color:var(--text-secondary); grid-column: 1 / -1;">Ürünler yüklenirken bir hata oluştu. Lütfen sayfayı yenileyin.</p>';
            productCount.textContent = '0 Ürün';
        }
    }

    // Render products to the grid
    function renderProducts(products) {
        productsGrid.innerHTML = '';
        
        if (products.length === 0) {
            productsGrid.innerHTML = '<p style="text-align:center; color:var(--text-secondary); grid-column: 1 / -1;">Aradığınız kriterlere uygun ürün bulunamadı.</p>';
            productCount.textContent = '0 Ürün';
            return;
        }

        productCount.textContent = `${products.length} Ürün Listeleniyor`;

        products.forEach(product => {
            const price = product.price ? `$${product.price.toFixed(2)}` : 'Fiyat Yok';
            const rating = product.rating ? `${product.rating} ★` : 'Yeni';
            const brand = product.brand ? product.brand : 'Genel';
            
            // Eğer resim URL'si yoksa veya hatalıysa yedek görsel kullan
            const imageUrl = product.image_url ? product.image_url : 'https://via.placeholder.com/250x250?text=Görsel+Yok';

            const card = document.createElement('div');
            card.className = 'product-card glass';
            card.innerHTML = `
                <img src="${imageUrl}" alt="${product.title}" class="product-image" loading="lazy" onerror="this.src='https://via.placeholder.com/250x250?text=Hata'">
                <div class="product-info">
                    <span class="product-brand">${brand}</span>
                    <h4 class="product-title">${product.title}</h4>
                    <div class="product-bottom">
                        <span class="product-price">${price}</span>
                        <span class="product-rating">${rating}</span>
                    </div>
                </div>
            `;
            productsGrid.appendChild(card);
        });
    }

    // Basic frontend search functionality
    function performSearch() {
        const query = searchInput.value.toLowerCase().trim();
        if (!query) {
            renderProducts(allProducts);
            return;
        }

        const filtered = allProducts.filter(product => {
            const titleMatch = product.title && product.title.toLowerCase().includes(query);
            const brandMatch = product.brand && product.brand.toLowerCase().includes(query);
            const catMatch = product.category && product.category.toLowerCase().includes(query);
            return titleMatch || brandMatch || catMatch;
        });

        renderProducts(filtered);
    }

    searchBtn.addEventListener('click', performSearch);
    searchInput.addEventListener('keyup', (e) => {
        if (e.key === 'Enter') performSearch();
    });

    // Init
    fetchProducts();
});
