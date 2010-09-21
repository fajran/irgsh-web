from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator, InvalidPage, EmptyPage
from django.utils.translation import ugettext as _
from django.contrib.auth import logout
from django.http import HttpResponseRedirect
from django.template import RequestContext

from settings import FULL_LOGOUT_URL

from jobs.forms import *
from jobs.models import *
from django.shortcuts import render_to_response
from django.forms.models import inlineformset_factory

def site_logout(request):
    logout(request)
    return render_to_response("logout.html", {
        "full_logout_url": FULL_LOGOUT_URL,
        },
        context_instance=RequestContext(request),
    )

def site_index(request):
    tasks_query = Task.objects.all().order_by('-id')[:5]

    return render_to_response("index.html", 
        {
            "tasks": tasks_query, 
        },
        context_instance=RequestContext(request),
    )

def tasks(request):
    tasks_query = Task.objects.all().order_by('-id')
    paginator = Paginator(tasks_query, 30)
    try:
        page = int(request.GET.get('page', '1'))
    except ValueError:
        page = 1

    try:
        tasks = paginator.page(page)
    except (EmptyPage, InvalidPage):
        tasks = paginator.page(paginator.num_pages)

    return render_to_response("tasks.html", 
        {
            "tasks": tasks, 
        },
        context_instance=RequestContext(request),
    )


def task(request, task_id):
    task_query = Task.objects.get(id=task_id)
    assignments_query = TaskAssignment.objects.filter(task=task_query)
    manifest_query = TaskManifest.objects.filter(task=task_query)
    log_query = TaskLog.objects.filter(task=task_query)
    return render_to_response("task.html", 
        { 
            "task_id": task_id,
            "task": task_query,
            "manifest": manifest_query,
            "assignments": assignments_query,
            "log": log_query,
        } ,
        context_instance=RequestContext(request),
    )
    
@login_required
def new_job(request):

    TasksInline = inlineformset_factory(Job, Task, extra=5,can_delete=False, formset=TaskInlineFormSet)

    if request.method == "POST":
        form = JobForm(request.POST)
        if form.is_valid():
            job = form.save(commit=False) 
            formset = TasksInline(request.POST, instance=job)
            if formset.is_valid():
                job.submitter = request.user
                job.save()
                formset.save()

                return render_to_response("new-job.html", {
                    "job_id": job.id
                    },
                    context_instance=RequestContext(request),
                )
        else:
            formset = TasksInline(instance=Job())
    else:
        form = JobForm()
        formset = TasksInline(instance=Job())

    return render_to_response("new-job.html", {
        "form": form,
        "formset": formset,
        },
        context_instance=RequestContext(request),
    )

#### XMLRPC starts here ####

def get_new_tasks():
    retval = []
    tasks = Task.objects.filter(state='N')
    for task in tasks:
        retval.append(task.id)
    return retval 

def get_task_info(task):
    task = Task.objects.get(id=task)
    log = TaskLog(task=task)
    
    retval = {
        'distribution': task.job.distro.name,
        'debian_url': task.debian_url,
        'debian_vcs': task.debian_vcs,
        'debian_tag': task.debian_tag,
        'orig_url': task.orig_url,
        'state': task.state,
        'debian_copy': task.debian_copy,
        'orig_copy': task.orig_copy,
    }

    return retval

def populate_debian_info(task_id, info):
    try:
        task = Task.objects.get(id=task_id)

        task.package = info["source"]
        task.version = info["version"]
        task.changelog = info["changelog"]

        for package in info["packages"]:
            m = TaskManifest()
            m.task = task
            m.name = package["package"]
            m.architecture = package["architecture"]
            if m.architecture == "source":
                m.type = 'S'
            else:
                m.type = 'B'
            m.save()

        task.save()
        log = TaskLog(task=task)
        log.log(_("Populated debian information"))
    except Exception as e:
        return (-1, str(e)) 
    return (0, "")


def set_debian_copy(task_id, url):
    try:
        task = Task.objects.get(id=task_id)
        task.debian_copy = url
        task.save()
        log = TaskLog(task=task)
        log.log(_("Set debian copy to %s" % url))
    except Exception as e:
        return (-1, str(e)) 
    return (0, "")


def set_orig_copy(task_id, url):
    try:
        task = Task.objects.get(id=task_id)
        task.orig_copy = url
        task.save()
        log = TaskLog(task=task)
        log.log(_("Set orig copy to %s" % url))
    except Exception as e:
        return (-1, str(e)) 
    return (0, "")

def start_running(task_id):
    try:
        task = Task.objects.get(id=task_id)
        task.start_running()
        log = TaskLog(task=task)
        log.log(_("Starting to run"))
    except Exception as e:
        return (-1, str(e)) 
    return (0, "")

def start_assigning(task_id):
    try:
        task = Task.objects.get(id=task_id)
        task.start_assigning()
        log = TaskLog(task=task)
        log.log(_("Starting to assign"))
    except Exception as e:
        return (-1, str(e)) 
    return (0, "")

def task_init_failed(task_id, message):
    try:
        task = Task.objects.get(id=task_id)
        task.fail(_("Task initialization failed: %s" % message))
    except Exception as e:
        return (-1, str(e)) 
    return (0, "")

def assign_task(task_id, handler):
    try:
        task_object = Task.objects.get(id=task_id)
        handler_object = Builder.objects.get(name=handler)
        architecture_object = handler_object.architecture
        assignment = TaskAssignment(task=task_object, architecture=architecture_object, handler=handler_object)
        assignment.save()
        log = TaskLog(task=task_object)
        log.log(_("Assigning task %d/%s to %s" % (task_id, str(handler_object.architecture), handler)))
        task_object.start_running()
    except Exception as e:
        return (-1, str(e)) 
    return (0, assignment.id)

def get_assignment_from_builder_and_task(task_id, handler):
    try:
        task_object = Task.objects.get(id=task_id)
        handler_object = Builder.objects.get(name=handler)
        architecture_object = handler_object.architecture
        assignment = TaskAssignment.objects.get(task=task_object, architecture=architecture_object, handler=handler_object)
    except Exception as e:
        return (-1, str(e)) 
    return (0, assignment.id)
        

def assignment_download(id):
    try:
        assignment = TaskAssignment.objects.get(id=id)
        assignment.start_downloading()
    except Exception as e:
        return (-1, str(e)) 
    return (0, "")

def assignment_environment(id):
    try:
        assignment = TaskAssignment.objects.get(id=id)
        assignment.start_environment()
    except Exception as e:
        return (-1, str(e)) 
    return (0, "")

def assignment_building(id):
    try:
        assignment = TaskAssignment.objects.get(id=id)
        assignment.start_building()
    except Exception as e:
        return (-1, str(e)) 
    return (0, "")

def assignment_upload(id):
    try:
        assignment = TaskAssignment.objects.get(id=id)
        assignment.start_uploading()
    except Exception as e:
        return (-1, str(e)) 
    return (0, "")

def assignment_complete(id):
    try:
        assignment = TaskAssignment.objects.get(id=id)
        assignment.start_completing()
    except Exception as e:
        return (-1, str(e)) 
    return (0, "")

def assignment_fail(id):
    try:
        assignment = TaskAssignment.objects.get(id=id)
        assignment.fail()
    except Exception as e:
        return (-1, str(e)) 
    return (0, "")


def assignment_set_log_url(id, url):
    try:
        assignment = TaskAssignment.objects.get(id=id)
        assignment.set_log_url(url)
    except Exception as e:
        return (-1, str(e)) 
    return (0, "")


def get_unassigned_task():
    id = -1
    try:
        task = Task.objects.filter(state='A').order_by('-id')[:1]
        if len(task) == 0:
            return (0, -1)
        id = task[0].id
    except Exception as e:
        return (-1, str(e)) 
    
    return (0, id)

#def ()
#    try:
#    except Exception as e:
#        return (-1, str(e)) 
#    return (0, "")



