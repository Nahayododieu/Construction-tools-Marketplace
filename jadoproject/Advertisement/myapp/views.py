from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, FormView, TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.auth.models import User
from django.contrib import messages
from django.urls import reverse_lazy, reverse
from django.http import HttpResponse, FileResponse
from django.views import View
from django.conf import settings
import os
import logging
from django.db import models, transaction
from .models import Product, Category, Comment, Message, Report, Share, Order, Cart, CartItem
from .forms import ProductForm, OrderForm, CancelOrderForm
from django.http import JsonResponse, HttpResponseForbidden
from .forms import CommentForm
from .forms import MessageForm
from .forms import ReportForm
from .forms import ShareForm
from .forms import RegularUserSignupForm
from .forms import EmailOrUsernameAuthenticationForm

logger = logging.getLogger('myapp.security')


class AdminOrOwnerMixin(UserPassesTestMixin):
    """Mixin to check if user is admin or owner of the advertisement"""
    def test_func(self):
        ad = self.get_object()
        # Allow if user is admin/staff or the owner
        return self.request.user.is_staff or self.request.user == ad.user
    
    def handle_no_permission(self):
        # Redirect to home if not authorized
        return redirect('advertisement-list')


class AdminOnlyMixin(UserPassesTestMixin):
    """Allow access to staff users only."""
    def test_func(self):
        user = self.request.user
        return user.is_authenticated and user.is_staff
    
    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return redirect('login')
        messages.error(self.request, 'You do not have permission to access the admin panel.')
        return redirect('advertisement-list')


class ApprovedOrStaffMixin(UserPassesTestMixin):
    """Allow access if user is staff or authenticated."""
    def test_func(self):
        user = self.request.user
        if not user.is_authenticated:
            return False
        if user.is_staff or user.is_superuser:
            return True
        # Allow all authenticated users since profile approval is removed
        return True
    
    def handle_no_permission(self):
        return redirect('advertisement-list')


class LandingPageView(TemplateView):
    template_name = 'myapp/landing.html'

    # The landing page is shown to all visitors (authenticated or not).
    # Users can still navigate to the advertisements list via the menu.
    construction_categories = [
        {
            'name': 'Cement & Concrete',
            'description': 'Bagged cement, ready-mix supplies, blocks, and finishing materials.',
            'accent': 'Sand Finish',
            'image': 'https://images.unsplash.com/photo-1513467535987-fd81bc7d62f8?auto=format&fit=crop&w=900&q=80',
        },
        {
            'name': 'Steel & Roofing',
            'description': 'Roof sheets, structural steel, gutters, and weather-ready framing.',
            'accent': 'Weather Shield',
            'image': 'https://images.unsplash.com/photo-1504307651254-35680f356dfd?auto=format&fit=crop&w=900&q=80',
        },
        {
            'name': 'Tiles & Flooring',
            'description': 'Porcelain tiles, floor finishes, adhesives, and trim for interiors.',
            'accent': 'Interior Finish',
            'image': 'https://images.unsplash.com/photo-1505693416388-ac5ce068fe85?auto=format&fit=crop&w=900&q=80',
        },
        {
            'name': 'Plumbing & Fittings',
            'description': 'Pipes, tanks, valves, and hardware for residential and site work.',
            'accent': 'Site Essentials',
            'image': 'https://images.unsplash.com/photo-1581093458791-9f3c3900df4b?auto=format&fit=crop&w=900&q=80',
        },
    ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        active_ads = Product.objects.filter(status='active').select_related('category', 'user')

        featured_ads = list(active_ads.order_by('-is_featured', '-created_at')[:6])
        recommended_ads = list(active_ads.order_by('-views', '-created_at')[:8])
        latest_ads = list(active_ads.order_by('-created_at')[:4])

        for item in featured_ads + recommended_ads + latest_ads:
            if not getattr(item, 'badge', None):
                item.badge = 'Featured' if item.is_featured else 'In Stock'

        db_categories = list(Category.objects.all()[:4])
        category_cards = []
        for index, category in enumerate(db_categories):
            fallback = self.construction_categories[index % len(self.construction_categories)]
            category_cards.append({
                'id': category.id,
                'name': category.name,
                'description': category.description or fallback['description'],
                'accent': fallback['accent'],
                'image': fallback['image'],
                'count': category.products.filter(status='active').count(),
            })

        if not category_cards:
            for fallback in self.construction_categories:
                category_cards.append({
                    'id': None,
                    'name': fallback['name'],
                    'description': fallback['description'],
                    'accent': fallback['accent'],
                    'image': fallback['image'],
                    'count': active_ads.count(),
                })

        context.update({
            'hero_stats': {
                'products': active_ads.count(),
                'categories': max(len(category_cards), Category.objects.count()),
                'cities': active_ads.values('city').distinct().count(),
            },
            'category_cards': category_cards,
            'featured_ads': featured_ads,
            'recommended_ads': recommended_ads,
            'latest_ads': latest_ads,
        })
        return context


class ProductListView(ListView):
    model = Product
    template_name = 'myapp/advertisement_list.html'
    context_object_name = 'advertisements'
    paginate_by = 10
    
    def get_queryset(self):
        queryset = Product.objects.select_related('category', 'user').all()
        category = self.request.GET.get('category')
        status = self.request.GET.get('status')
        search = self.request.GET.get('search')

        if not self.request.user.is_staff:
            queryset = queryset.filter(status='active', stock_quantity__gt=0)
        
        if category:
            queryset = queryset.filter(category_id=category)
        if status and self.request.user.is_staff:
            queryset = queryset.filter(status=status)
        if search:
            queryset = queryset.filter(
                models.Q(title__icontains=search) |
                models.Q(description__icontains=search) |
                models.Q(city__icontains=search) |
                models.Q(category__name__icontains=search)
            )
        
        return queryset.order_by('-created_at')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categories'] = Category.objects.all()
        return context


class ProductDetailView(DetailView):
    model = Product
    template_name = 'myapp/advertisement_detail.html'
    context_object_name = 'advertisement'
    slug_field = 'slug'
    slug_url_kwarg = 'slug'

    def get_queryset(self):
        queryset = Product.objects.select_related('category', 'user')
        if self.request.user.is_staff:
            return queryset
        return queryset.filter(status='active', stock_quantity__gt=0)
    
    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        obj.views += 1
        obj.save()
        return obj


class ToggleLikeView(View):
    def post(self, request, slug):
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'login_required'}, status=403)
        ad = get_object_or_404(Product, slug=slug)
        user = request.user
        if user in ad.likes.all():
            ad.likes.remove(user)
            liked = False
        else:
            ad.likes.add(user)
            liked = True
        return JsonResponse({'liked': liked, 'total_likes': ad.likes.count()})


class IncrementShareView(View):
    def post(self, request, slug):
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'login_required'}, status=403)

        ad = get_object_or_404(Product, slug=slug)
        share_method = request.POST.get('share_method', 'link')

        # Create or get share record
        share, created = Share.objects.get_or_create(
            user=request.user,
            advertisement=ad,
            share_method=share_method,
            defaults={
                'ip_address': self.get_client_ip(request),
                'user_agent': request.META.get('HTTP_USER_AGENT', '')
            }
        )

        if created:
            ad.refresh_from_db(fields=['shares_count'])

        return JsonResponse({
            'shares_count': ad.shares_count,
            'created': created
        })

    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class ShareAnalyticsView(AdminOnlyMixin, TemplateView):
    template_name = 'myapp/share_analytics.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Share statistics
        context['total_shares'] = Share.objects.count()
        context['unique_sharers'] = Share.objects.values('user').distinct().count()
        context['most_shared_ads'] = Product.objects.annotate(
            share_count=models.Count('shares')
        ).order_by('-share_count')[:10]

        # Shares by method
        shares_by_method = Share.objects.values('share_method').annotate(
            count=models.Count('share_method')
        ).order_by('-count')
        
        # Calculate percentage for each method
        total_shares = context['total_shares']
        for method in shares_by_method:
            if total_shares > 0:
                method['percentage'] = round((method['count'] / total_shares) * 100, 1)
            else:
                method['percentage'] = 0
        
        context['shares_by_method'] = shares_by_method

        # Recent shares
        context['recent_shares'] = Share.objects.select_related('user', 'advertisement')[:20]

        # Shares over time (last 30 days)
        from django.utils import timezone
        from datetime import timedelta

        thirty_days_ago = timezone.now() - timedelta(days=30)
        context['shares_last_30_days'] = Share.objects.filter(
            shared_at__gte=thirty_days_ago
        ).count()

        return context


class UserShareHistoryView(LoginRequiredMixin, ListView):
    model = Share
    template_name = 'myapp/user_share_history.html'
    context_object_name = 'shares'
    paginate_by = 20

    def get_queryset(self):
        return Share.objects.filter(user=self.request.user).select_related('advertisement')


class UserProfileView(LoginRequiredMixin, TemplateView):
    """User profile page for viewing and editing user information"""
    template_name = 'myapp/user_profile.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        # Get user statistics
        context['user'] = user
        context['total_ads'] = Product.objects.filter(user=user).count()
        context['active_ads'] = Product.objects.filter(user=user, status='active').count()
        context['total_views'] = Product.objects.filter(user=user).aggregate(
            total=models.Sum('views')
        )['total'] or 0
        context['total_likes'] = Product.objects.filter(user=user).aggregate(
            total=models.Count('likes', distinct=True)
        )['total'] or 0
        context['member_since'] = user.date_joined.strftime('%B %Y')
        
        return context


class UserRolesView(TemplateView):
    """Display user roles and permissions information"""
    template_name = 'myapp/user_roles.html'


class AddCommentView(View):
    def post(self, request, slug):
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'login_required'}, status=403)
        ad = get_object_or_404(Product, slug=slug)
        form = CommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.user = request.user
            comment.ad = ad

            # Handle parent comment for replies
            parent_id = request.POST.get('parent_id')
            if parent_id:
                try:
                    parent_comment = Comment.objects.get(id=parent_id, ad=ad)
                    comment.parent = parent_comment
                except Comment.DoesNotExist:
                    return JsonResponse({'error': 'Parent comment not found'}, status=400)

            comment.save()

            return JsonResponse({
                'ok': True,
                'comment_id': comment.id,
                'username': request.user.username,
                'text': comment.text,
                'created_at': comment.created_at.strftime('%Y-%m-%d %H:%M'),
                'is_reply': comment.is_reply(),
                'parent_id': parent_id or None
            })
        return JsonResponse({'ok': False, 'errors': form.errors}, status=400)


class ProductCreateView(LoginRequiredMixin, AdminOnlyMixin, CreateView):
    model = Product
    template_name = 'myapp/advertisement_form.html'
    form_class = ProductForm
    success_url = reverse_lazy('advertisement-list')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({'user': self.request.user})
        return kwargs

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)


class ProductUpdateView(LoginRequiredMixin, AdminOnlyMixin, UpdateView):
    model = Product
    template_name = 'myapp/advertisement_form.html'
    form_class = ProductForm
    slug_field = 'slug'
    slug_url_kwarg = 'slug'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({'user': self.request.user})
        return kwargs

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('advertisement-detail', kwargs={'slug': self.object.slug})


class ProductDeleteView(LoginRequiredMixin, AdminOnlyMixin, DeleteView):
    model = Product
    template_name = 'myapp/advertisement_confirm_delete.html'
    slug_field = 'slug'
    slug_url_kwarg = 'slug'
    success_url = reverse_lazy('advertisement-list')


class CategoryListView(ListView):
    model = Category
    template_name = 'myapp/category_list.html'
    context_object_name = 'categories'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        for category in context['categories']:
            category.ad_count = category.products.filter(status='active').count()
        context['total_ads'] = Product.objects.filter(status='active').count()
        return context


class DownloadProductImageView(View):
    """View to download advertisement image"""
    def get(self, request, slug):
        advertisement = get_object_or_404(Product, slug=slug)
        
        if not advertisement.image:
            return HttpResponse("No image available", status=404)
        
        file_path = advertisement.image.path
        
        if not os.path.exists(file_path):
            return HttpResponse("Image file not found", status=404)
        
        # Get the filename
        filename = os.path.basename(file_path)
        
        # Open and serve the file
        with open(file_path, 'rb') as f:
            response = HttpResponse(f.read(), content_type='application/octet-stream')
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response


class CustomLoginView(LoginView):
    """Custom login view"""
    template_name = 'myapp/login.html'
    form_class = EmailOrUsernameAuthenticationForm
    # After login, send the user to the dashboard.
    # The landing page stays as home for logged-out visitors.
    success_url = reverse_lazy('user-dashboard')
    
    def get_success_url(self):
        if self.request.user.is_staff:
            return reverse_lazy('admin-dashboard')
        return self.success_url
    
    def form_valid(self, form):
        """Log successful login"""
        response = super().form_valid(form)
        logger.info(f'Successful login for user: {self.request.user.username} from IP: {self.get_client_ip()}')
        return response
    
    def form_invalid(self, form):
        """Log failed login attempt"""
        logger.warning(f'Failed login attempt for username: {form.data.get("username")} from IP: {self.get_client_ip()}')
        return super().form_invalid(form)
    
    def get_client_ip(self):
        x_forwarded_for = self.request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = self.request.META.get('REMOTE_ADDR')
        return ip


class CustomLogoutView(LogoutView):
    """Custom logout view"""

    # Allow logout via GET as well as POST so the header link can log users out.
    # We override GET to mirror the POST behavior (logout + redirect).
    next_page = reverse_lazy('landing')
    http_method_names = ['get', 'post', 'options']

    def get(self, request, *args, **kwargs):
        return self.post(request, *args, **kwargs)


class SignupView(CreateView):
    """User registration view - creates regular users only"""
    form_class = RegularUserSignupForm
    template_name = 'myapp/signup.html'
    success_url = reverse_lazy('login')
    
    def form_valid(self, form):
        """Create regular user account"""
        # Check if terms were accepted
        if not self.request.POST.get('accept_terms'):
            from django.contrib import messages
            messages.error(self.request, 'You must accept the Terms & Conditions to create an account.')
            return self.form_invalid(form)
            
        self.object = form.save()
        
        logger.info(f'New regular user account created: {self.object.username} from IP: {self.get_client_ip()}')
        return redirect(self.get_success_url())

    def dispatch(self, request, *args, **kwargs):
        """Block or redirect signup attempts originating from the admin portal.

        We check the HTTP Referer and the `next` GET parameter for the
        admin portal token. If found, redirect to the advertisement list to
        avoid allowing signups coming from the admin area.
        """
        referer = request.META.get('HTTP_REFERER', '')
        next_param = request.GET.get('next', '')
        if 'admin-portal' in referer or 'admin-portal' in next_param:
            logger.warning(f'Blocked signup attempt from admin area from IP: {self.get_client_ip()}')
            return HttpResponse('Forbidden', status=403)
        return super().dispatch(request, *args, **kwargs)
    
    def get_client_ip(self):
        x_forwarded_for = self.request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = self.request.META.get('REMOTE_ADDR')
        return ip


# -------------------------  
# MESSAGING VIEWS
# -------------------------
class InboxView(LoginRequiredMixin, ListView):
    model = Message
    template_name = 'myapp/inbox.html'
    context_object_name = 'messages'
    paginate_by = 20

    def get_queryset(self):
        return Message.objects.filter(receiver=self.request.user).order_by('-created_at')


class SentMessagesView(LoginRequiredMixin, ListView):
    model = Message
    template_name = 'myapp/sent_messages.html'
    context_object_name = 'messages'
    paginate_by = 20

    def get_queryset(self):
        return Message.objects.filter(sender=self.request.user).order_by('-created_at')


class ComposeMessageView(LoginRequiredMixin, CreateView):
    model = Message
    form_class = MessageForm
    template_name = 'myapp/compose_message.html'
    success_url = reverse_lazy('inbox')

    def form_valid(self, form):
        form.instance.sender = self.request.user
        return super().form_valid(form)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_initial(self):
        initial = super().get_initial()
        receiver_id = self.request.GET.get('receiver')
        ad_id = self.request.GET.get('ad')
        if receiver_id:
            try:
                initial['receiver'] = User.objects.get(id=receiver_id)
            except User.DoesNotExist:
                pass
        if ad_id:
            try:
                initial['ad'] = Product.objects.get(id=ad_id)
            except Product.DoesNotExist:
                pass
        return initial


class MessageDetailView(LoginRequiredMixin, DetailView):
    model = Message
    template_name = 'myapp/message_detail.html'
    context_object_name = 'message'

    def get_queryset(self):
        # Only allow viewing messages sent to or from the user
        return Message.objects.filter(
            models.Q(sender=self.request.user) | models.Q(receiver=self.request.user)
        )

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        # Mark as read if the user is the receiver
        if obj.receiver == self.request.user and not obj.is_read:
            obj.is_read = True
            obj.save()
        return obj


# -------------------------
# REPORTING VIEWS
# -------------------------
class ReportProductView(LoginRequiredMixin, CreateView):
    model = Report
    form_class = ReportForm
    template_name = 'myapp/report_ad.html'

    def dispatch(self, request, *args, **kwargs):
        # Ensure advert exists before rendering
        self.ad = get_object_or_404(Product, slug=kwargs.get('slug'))
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['advertisement'] = self.ad
        return context

    def form_valid(self, form):
        form.instance.reporter = self.request.user
        form.instance.advertisement = self.ad
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('advertisement-detail', kwargs={'slug': self.ad.slug})


class ReportListView(AdminOnlyMixin, ListView):
    model = Report
    template_name = 'myapp/admin_reports.html'
    context_object_name = 'reports'
    paginate_by = 20

    def get_queryset(self):
        status = self.request.GET.get('status')
        report_type = self.request.GET.get('type')
        queryset = Report.objects.select_related('reporter', 'advertisement', 'advertisement__user')

        if status:
            queryset = queryset.filter(status=status)
        if report_type:
            queryset = queryset.filter(report_type=report_type)

        return queryset.order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['status_choices'] = Report.STATUS_CHOICES
        context['report_type_choices'] = Report.REPORT_TYPES
        return context


class ReportDetailView(AdminOnlyMixin, DetailView):
    model = Report
    template_name = 'myapp/admin_report_detail.html'
    context_object_name = 'report'


class UpdateReportStatusView(AdminOnlyMixin, View):
    def post(self, request, pk):
        report = get_object_or_404(Report, pk=pk)
        new_status = request.POST.get('status')
        admin_notes = request.POST.get('admin_notes', '')

        if new_status in dict(Report.STATUS_CHOICES):
            report.status = new_status
            report.admin_notes = admin_notes
            report.save()

        return redirect('admin-report-detail', pk=pk)


class UserDashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'myapp/user_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        # User's advertisements
        context['user_ads'] = Product.objects.filter(user=user).order_by('-created_at')
        context['active_ads_count'] = context['user_ads'].filter(status='active').count()
        context['sold_ads_count'] = context['user_ads'].filter(status='sold').count()
        context['total_views'] = context['user_ads'].aggregate(total=models.Sum('views'))['total'] or 0
        context['total_likes'] = context['user_ads'].aggregate(
            total=models.Count('likes', distinct=True)
        )['total'] or 0

        # User's activity
        context['user_messages'] = Message.objects.filter(
            models.Q(sender=user) | models.Q(receiver=user)
        ).order_by('-created_at')[:5]

        context['user_reports'] = Report.objects.filter(reporter=user).order_by('-created_at')[:5]
        context['user_shares'] = Share.objects.filter(user=user).select_related('advertisement').order_by('-shared_at')[:10]
        context['recent_orders'] = Order.objects.filter(user=user).select_related('advertisement').order_by('-created_at')[:5]
        context['cart_items_count'] = Cart.objects.filter(user=user).first().get_total_items() if Cart.objects.filter(user=user).exists() else 0

        # Recent comments on user's ads
        context['recent_comments'] = Comment.objects.filter(
            ad__user=user
        ).select_related('user', 'ad').order_by('-created_at')[:10]

        return context


class AdminDashboardView(AdminOnlyMixin, TemplateView):
    template_name = 'myapp/admin_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Basic statistics
        context['total_ads'] = Product.objects.count()
        context['active_ads'] = Product.objects.filter(status='active').count()
        context['pending_ads'] = Product.objects.filter(status='pending').count()
        context['sold_ads'] = Product.objects.filter(status='sold').count()
        context['expired_ads'] = Product.objects.filter(status='expired').count()

        context['total_users'] = User.objects.count()
        context['staff_users'] = User.objects.filter(is_staff=True).count()
        context['active_users'] = User.objects.filter(is_active=True).count()
        context['inactive_users'] = User.objects.filter(is_active=False).count()

        context['categories_count'] = Category.objects.count()
        context['total_orders'] = Order.objects.count()
        context['pending_orders'] = Order.objects.filter(status='pending').count()
        context['completed_orders'] = Order.objects.filter(status='completed').count()
        context['customer_accounts'] = User.objects.filter(is_staff=False).count()

        context['recent_ads'] = Product.objects.select_related('user').order_by('-created_at')[:10]
        context['recent_users'] = User.objects.order_by('-date_joined')[:10]
        context['recent_orders'] = Order.objects.select_related('user', 'advertisement').order_by('-created_at')[:10]
        context['most_viewed_ads'] = Product.objects.select_related('user').order_by('-views', '-created_at')[:5]
        context['most_active_users'] = User.objects.annotate(
            ad_count=models.Count('ads')
        ).filter(ad_count__gt=0).order_by('-ad_count', 'username')[:5]

        context['ads_by_status'] = Product.objects.values('status').annotate(count=models.Count('status'))
        return context


class AdminUserManagementView(AdminOnlyMixin, ListView):
    model = User
    template_name = 'myapp/admin_users.html'
    context_object_name = 'users'
    paginate_by = 20

    def get_queryset(self):
        queryset = User.objects.all().order_by('-date_joined')
        search = self.request.GET.get('search')
        status = self.request.GET.get('status')
        is_staff = self.request.GET.get('is_staff')

        if search:
            queryset = queryset.filter(
                models.Q(username__icontains=search) |
                models.Q(email__icontains=search) |
                models.Q(first_name__icontains=search) |
                models.Q(last_name__icontains=search)
            )
        if status:
            if status == 'active':
                queryset = queryset.filter(is_active=True)
            elif status == 'inactive':
                queryset = queryset.filter(is_active=False)
        if is_staff:
            if is_staff == 'staff':
                queryset = queryset.filter(is_staff=True)
            elif is_staff == 'user':
                queryset = queryset.filter(is_staff=False)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['total_users'] = User.objects.count()
        context['active_users'] = User.objects.filter(is_active=True).count()
        context['inactive_users'] = User.objects.filter(is_active=False).count()
        context['staff_users'] = User.objects.filter(is_staff=True).count()
        return context


class AdminProductManagementView(AdminOnlyMixin, ListView):
    model = Product
    template_name = 'myapp/admin_ads.html'
    context_object_name = 'advertisements'
    paginate_by = 20

    def get_queryset(self):
        queryset = Product.objects.select_related('user', 'category').order_by('-created_at')
        search = self.request.GET.get('search')
        status = self.request.GET.get('status')
        category = self.request.GET.get('category')

        if search:
            queryset = queryset.filter(
                models.Q(title__icontains=search) |
                models.Q(description__icontains=search) |
                models.Q(user__username__icontains=search)
            )
        if status:
            queryset = queryset.filter(status=status)
        if category:
            queryset = queryset.filter(category_id=category)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categories'] = Category.objects.all()
        context['status_choices'] = Product.STATUS_CHOICES
        return context


class AdminUpdateAdStatusView(AdminOnlyMixin, View):
    def post(self, request, pk):
        ad = get_object_or_404(Product, pk=pk)
        new_status = request.POST.get('status')
        
        if new_status in dict(Product.STATUS_CHOICES):
            ad.status = new_status
            ad.save()
        
        return redirect('admin-ads')


class AdminToggleUserStatusView(AdminOnlyMixin, View):
    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        user.is_active = not user.is_active
        user.save()
        
        return redirect('admin-users')


class UserSignupsListView(AdminOnlyMixin, ListView):
    """Admin view to retrieve and display all user signups (registrations)"""
    model = User
    template_name = 'myapp/user_signups.html'
    context_object_name = 'users'
    paginate_by = 20

    def get_queryset(self):
        queryset = User.objects.all().order_by('-date_joined')
        search = self.request.GET.get('search')
        status = self.request.GET.get('status')

        if search:
            queryset = queryset.filter(
                models.Q(username__icontains=search) |
                models.Q(email__icontains=search) |
                models.Q(first_name__icontains=search) |
                models.Q(last_name__icontains=search)
            )
        if status:
            if status == 'active':
                queryset = queryset.filter(is_active=True)
            elif status == 'inactive':
                queryset = queryset.filter(is_active=False)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['total_signups'] = User.objects.count()
        context['recent_signups'] = User.objects.order_by('-date_joined')[:10]
        return context


class AdminPasswordCheckView(View):
    """View to check admin password for accessing restricted features"""
    
    def get(self, request):
        next_url = request.GET.get('next', reverse('advertisement-list'))
        # Always show password form for security
        return render(request, 'myapp/admin_password_check.html', {
            'next': next_url
        })
    
    def post(self, request):
        next_url = request.POST.get('next', reverse('advertisement-list'))
        password = request.POST.get('password', '')

        if password == settings.ADMIN_ACCESS_PASSWORD:
            # Set session flag for temporary access
            request.session['admin_access_granted'] = True
            request.session.set_expiry(3600)  # 1 hour
            return redirect(next_url)
        else:
            messages.error(request, 'Incorrect admin password.')
            return render(request, 'myapp/admin_password_check.html', {
                'next': next_url
            })


class OrderFormView(LoginRequiredMixin, FormView):
    """Display order form and create Order record."""
    template_name = 'myapp/order_form.html'
    form_class = OrderForm
    login_url = 'login'

    def dispatch(self, request, *args, **kwargs):
        # Ensure advert exists before rendering
        self.ad = get_object_or_404(Product, slug=kwargs.get('slug'))
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.setdefault('initial', {})
        kwargs['initial'].update({
            'buyer_name': self.request.user.get_full_name() or self.request.user.username,
            'buyer_email': self.request.user.email,
        })
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['advertisement'] = self.ad
        context['action'] = 'order'
        return context

    def form_valid(self, form):
        quantity = form.cleaned_data['quantity']
        if quantity > self.ad.stock_quantity:
            form.add_error('quantity', f'Only {self.ad.stock_quantity} item(s) are currently available.')
            return self.form_invalid(form)

        order = Order.objects.create(
            user=self.request.user,
            advertisement=self.ad,
            quantity=quantity,
            status='pending'
        )
        return render(self.request, 'myapp/order_success.html', {
            'advertisement': self.ad,
            'order': order,
            'action': 'order'
        })


class BuyNowFormView(LoginRequiredMixin, FormView):
    """Display buy-now form and create completed Order."""
    template_name = 'myapp/order_form.html'
    form_class = OrderForm
    login_url = 'login'

    def dispatch(self, request, *args, **kwargs):
        self.ad = get_object_or_404(Product, slug=kwargs.get('slug'))
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.setdefault('initial', {})
        kwargs['initial'].update({
            'buyer_name': self.request.user.get_full_name() or self.request.user.username,
            'buyer_email': self.request.user.email,
        })
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['advertisement'] = self.ad
        context['action'] = 'buy'
        return context

    def form_valid(self, form):
        quantity = form.cleaned_data['quantity']
        if quantity > self.ad.stock_quantity:
            form.add_error('quantity', f'Only {self.ad.stock_quantity} item(s) are currently available.')
            return self.form_invalid(form)

        try:
            self.ad.reduce_stock(quantity)
        except ValueError as exc:
            form.add_error('quantity', str(exc))
            return self.form_invalid(form)

        order = Order.objects.create(
            user=self.request.user,
            advertisement=self.ad,
            quantity=quantity,
            status='completed'
        )
        self.ad.refresh_from_db(fields=['stock_quantity'])
        return render(self.request, 'myapp/order_success.html', {
            'advertisement': self.ad,
            'order': order,
            'action': 'buy',
            'remaining_stock': self.ad.stock_quantity,
        })


class CancelOrderView(LoginRequiredMixin, FormView):
    template_name = 'myapp/cancel_order.html'
    form_class = CancelOrderForm

    def dispatch(self, request, *args, **kwargs):
        self.order = get_object_or_404(
            Order.objects.select_related('advertisement'),
            pk=kwargs.get('pk'),
            user=request.user,
        )
        if self.order.status == 'cancelled':
            messages.info(request, 'This order has already been cancelled.')
            return redirect('user-dashboard')
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['order'] = self.order
        return context

    def form_valid(self, form):
        restore_stock = self.order.status == 'completed'
        self.order.status = 'cancelled'
        self.order.cancellation_reason = form.cleaned_data['cancellation_reason']
        self.order.save(update_fields=['status', 'cancellation_reason'])
        if restore_stock:
            self.order.advertisement.restore_stock(self.order.quantity)
        messages.success(self.request, 'Your order was cancelled successfully.')
        return redirect('user-dashboard')


# -------------------------  
# CART VIEWS
# -------------------------
class AddToCartView(View):
    def post(self, request, slug):
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'login_required'}, status=403)

        ad = get_object_or_404(Product, slug=slug)
        try:
            quantity = int(request.POST.get('quantity', 1))
        except (TypeError, ValueError):
            return JsonResponse({'error': 'invalid_quantity'}, status=400)

        if quantity < 1:
            return JsonResponse({'error': 'invalid_quantity'}, status=400)

        # Get or create cart for user
        cart, created = Cart.objects.get_or_create(user=request.user)

        existing_quantity = cart.items.filter(advertisement=ad).values_list('quantity', flat=True).first() or 0
        requested_total = existing_quantity + quantity
        if requested_total > ad.stock_quantity:
            return JsonResponse({
                'error': f'Only {ad.stock_quantity} item(s) are available in stock.'
            }, status=400)
        
        # Get or create cart item
        cart_item, item_created = CartItem.objects.get_or_create(
            cart=cart,
            advertisement=ad,
            defaults={'quantity': quantity}
        )
        
        if not item_created:
            cart_item.quantity += quantity
            cart_item.save()
        
        return JsonResponse({
            'success': True,
            'cart_total_items': cart.get_total_items(),
            'cart_total_price': float(cart.get_total_price())
        })


class CartView(LoginRequiredMixin, TemplateView):
    template_name = 'myapp/cart.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cart, created = Cart.objects.get_or_create(user=self.request.user)
        context['cart'] = cart
        context['cart_items'] = cart.items.select_related('advertisement').all()
        return context


class UpdateCartItemView(LoginRequiredMixin, View):
    def post(self, request, item_id):
        cart_item = get_object_or_404(CartItem, id=item_id, cart__user=request.user)
        try:
            quantity = int(request.POST.get('quantity', 1))
        except (TypeError, ValueError):
            return JsonResponse({'error': 'invalid_quantity'}, status=400)

        if quantity > cart_item.advertisement.stock_quantity:
            return JsonResponse({
                'error': f'Only {cart_item.advertisement.stock_quantity} item(s) are available in stock.'
            }, status=400)

        if quantity > 0:
            cart_item.quantity = quantity
            cart_item.save()
        else:
            cart_item.delete()
        
        cart = cart_item.cart
        return JsonResponse({
            'success': True,
            'item_total': float(cart_item.get_total_price()) if quantity > 0 else 0,
            'cart_total_items': cart.get_total_items(),
            'cart_total_price': float(cart.get_total_price())
        })


class RemoveCartItemView(LoginRequiredMixin, View):
    def post(self, request, item_id):
        cart_item = get_object_or_404(CartItem, id=item_id, cart__user=request.user)
        cart = cart_item.cart
        cart_item.delete()
        
        return JsonResponse({
            'success': True,
            'cart_total_items': cart.get_total_items(),
            'cart_total_price': float(cart.get_total_price())
        })


class CheckoutView(LoginRequiredMixin, TemplateView):
    template_name = 'myapp/checkout.html'

    def dispatch(self, request, *args, **kwargs):
        cart, created = Cart.objects.get_or_create(user=request.user)
        if not cart.items.exists():
            return redirect('cart')
        return super().dispatch(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cart, created = Cart.objects.get_or_create(user=self.request.user)
        context['cart'] = cart
        context['cart_items'] = cart.items.select_related('advertisement').all()
        return context


class ProcessCheckoutView(LoginRequiredMixin, View):
    def post(self, request):
        cart = get_object_or_404(Cart, user=request.user)
        if not cart.items.exists():
            return redirect('cart')
        
        # Validate form data
        buyer_name = request.POST.get('buyer_name')
        buyer_email = request.POST.get('buyer_email')
        payment_method = request.POST.get('payment_method')
        shipping_address = request.POST.get('shipping_address')
        notes = request.POST.get('notes', '')
        
        if not all([buyer_name, buyer_email, payment_method, shipping_address]):
            messages.error(request, 'Please fill in all required fields.')
            return redirect('checkout')
        
        orders = []
        cart_items = list(cart.items.select_related('advertisement').all())
        total_items_purchased = sum(item.quantity for item in cart_items)
        total_amount = sum(
            item.advertisement.price * item.quantity for item in cart_items
        )

        try:
            with transaction.atomic():
                for item in cart_items:
                    locked_product = Product.objects.select_for_update().get(pk=item.advertisement_id)
                    if item.quantity > locked_product.stock_quantity:
                        messages.error(
                            request,
                            f'{locked_product.title} only has {locked_product.stock_quantity} item(s) available.'
                        )
                        return redirect('cart')

                for item in cart_items:
                    item.advertisement.reduce_stock(item.quantity)
                    order = Order.objects.create(
                        user=request.user,
                        advertisement=item.advertisement,
                        quantity=item.quantity,
                        status='completed'
                    )
                    orders.append(order)

                cart.items.all().delete()
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect('cart')
        
        return render(request, 'myapp/checkout_success.html', {
            'orders': orders,
            'total_items_purchased': total_items_purchased,
            'total_amount': total_amount,
        })


AdvertisementListView = ProductListView
AdvertisementDetailView = ProductDetailView
AdvertisementCreateView = ProductCreateView
AdvertisementUpdateView = ProductUpdateView
AdvertisementDeleteView = ProductDeleteView
DownloadAdvertisementImageView = DownloadProductImageView
ReportAdvertisementView = ReportProductView
AdminAdvertisementManagementView = AdminProductManagementView
